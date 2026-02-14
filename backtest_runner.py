import asyncio
import logging
from datetime import datetime
from playwright.async_api import Page
from browser_manager import BrowserManager
from schemas import Strategy
from config import config

logger = logging.getLogger(__name__)

class BacktestRunner:
    def __init__(self, browser_manager: BrowserManager):
        self.bm = browser_manager

    async def apply_base_settings(self, timeframe="5 Min", lookback="1 Year"):
        """Settings: BTC, timeframe, lookback, Normalize"""
        try:
            await self.bm.select_dropdown_option("Ticker", "BTC", index=0)
            await self.bm.select_dropdown_option("TimeFrame", timeframe, index=1)
            await self.bm.select_dropdown_option("Lookback", lookback, index=2)
            await self.bm.toggle_normalize()
        except Exception as e:
            logger.error(f"Base settings failed: {e}")

    async def configure_indicator_row(self, indicator_name: str, operator: str, value: float, row_index: int):
        """
        Configures the specific row for an indicator based on provided HTML structure.
        Finds the <p> label, then the two associated inputs (Min, Max).
        """
        page = self.bm.page
        logger.info(f"Configuring {indicator_name}: {operator} {value}")
        
        try:
            # 1. Find the label using the provided class or text
            # Using specific class from user feedback: "MuiTypography-root"
            # We look for a <p> tag containing the exact indicator name
            
            label = page.locator(f"p.MuiTypography-root:has-text('{indicator_name}')").last
            
            if await label.count() > 0:
                # 2. Find the inputs associated with this label.
                # Based on HTML, inputs seem to be siblings or in the same parent container row.
                # We go up to the parent row.
                
                # Assuming the structure is: Row -> [Label] [Slider/Inputs]
                parent_row = label.locator("..").locator("..") # Go up 2 levels to be safe
                
                # Find inputs within this row context
                # We filter for inputs that have value attributes or type number
                inputs = parent_row.locator("input[type='number']")
                
                # We expect exactly 2 inputs per row (Min and Max)
                # But parent_row might be too broad.
                
                # Alternative: Use 'xpath' to find following inputs relative to the label p tag
                # The inputs come AFTER the p tag in the DOM flow.
                
                min_input = label.locator("xpath=following::input[@type='number'][1]")
                max_input = label.locator("xpath=following::input[@type='number'][2]")
                
                if await min_input.count() > 0 and await max_input.count() > 0:
                    
                    # Logic for > and <
                    if ">" in operator:
                        # Greater than X -> Min = X, Max = 100
                        await min_input.fill(str(value))
                        await max_input.fill("100")
                        logger.info(f"Set {indicator_name} RANGE: {value} to 100")
                        
                    elif "<" in operator:
                        # Less than Y -> Min = 0, Max = Y
                        await min_input.fill("0")
                        await max_input.fill(str(value))
                        logger.info(f"Set {indicator_name} RANGE: 0 to {value}")
                else:
                    logger.warning(f"Could not find Min/Max inputs for {indicator_name}")
            else:
                logger.warning(f"Indicator label '{indicator_name}' not found.")

        except Exception as e:
            logger.warning(f"Failed config for {indicator_name}: {e}")

    async def run_strategy(self, strategy: Strategy, timeframe="5 Min", lookback="1 Year") -> dict:
        page = self.bm.page
        if not page: raise RuntimeError("No Page")
        
        if "login" in page.url.lower():
            logger.warning("Logged out during execution. Re-authenticating...")
            await self.bm.ensure_login()

        # Refresh page to clear state (indicators, inputs, etc.)
        logger.info("Refreshing page to clear state...")
        await page.reload(wait_until="domcontentloaded")
        await asyncio.sleep(3) # Wait for app to re-init

        logger.info(f"Running: {strategy.name} ({strategy.direction}) [{timeframe}, {lookback}]")
        
        try:
            await self.apply_base_settings(timeframe=timeframe, lookback=lookback)
            
            # Set Indicators
            # 1. Open the Indicators Dropdown
            logger.info("Opening Indicators Dropdown...")
            
            # Try to find the autocomplete input directly
            ind_input = page.locator("input[placeholder='Indicators'], input[id*='indicators']")
            if await ind_input.count() > 0:
                 await ind_input.first.click()
            else:
                # Fallback to index 3
                await self.bm.select_dropdown_option("Indicators", None, index=3, open_only=True)
            
            # 2. Wait for dropdown to open
            await asyncio.sleep(1.5)
            
            # 3. Select Items (No manual clearing needed after refresh)
            for i, ind in enumerate(strategy.indicators):
                if ind.name == "None" or not ind.name:
                    continue

                logger.info(f"Selecting {ind.name}...")
                try:
                    await self.bm.select_item_in_open_listbox(ind.name)
                    # Small pause between selections
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Could not select {ind.name}: {e}")
            
            # 4. Close the dropdown (Click title or Press Escape)
            logger.info("Closing dropdown...")
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)
            
            # --- Click Continue ---
            logger.info("Checking for 'Continue' button...")
            try:
                continue_btn = page.locator("button.backtester-indication-button")
                if await continue_btn.count() == 0:
                    continue_btn = page.locator("button:has-text('Continue')")
                
                if await continue_btn.count() > 0:
                    logger.info("Clicking 'Continue'...")
                    await continue_btn.click()
                    await asyncio.sleep(2) 
                else:
                    logger.warning("'Continue' button not found.")
            except Exception as e:
                logger.warning(f"Continue button interaction failed: {e}")

            # 4. Configure Thresholds (Now that they are added to the view)
            for i, ind in enumerate(strategy.indicators):
                await self.configure_indicator_row(ind.name, ind.operator, ind.threshold_value, i)

            # Set Direction & Risk
            try:
                # 1. Set Direction (Long/Short)
                target_value = strategy.direction.lower() 
                direction_btn = page.locator(f"button[value='{target_value}']")
                await direction_btn.click(force=True)
                logger.info(f"Set Direction to {strategy.direction}")

                # 2. Set Advanced Settings (Portfolio 1%)
                # Toggle Advance setting ON
                adv_switch_input = page.locator("input.MuiSwitch-input").last
                if await adv_switch_input.count() > 0:
                    if not await adv_switch_input.is_checked():
                        await adv_switch_input.locator("..").click(force=True)
                        await asyncio.sleep(0.5)

                # Set Portfolio % to 100
                portfolio_input = page.locator("input[max='100'][value='100']").last
                if await portfolio_input.count() == 0:
                     portfolio_input = page.locator("input[max='100']").last
                
                await portfolio_input.fill("100")
                logger.info("Set Portfolio Size to 100%")
                
                # 3. TP / SL
                tp_input = page.locator("text=Take Profit").locator("xpath=following::input[@type='number'][1]")
                await tp_input.fill(str(strategy.take_profit_pct))
                
                sl_input = page.locator("text=Stop Loss").locator("xpath=following::input[@type='number'][1]")
                await sl_input.fill(str(strategy.stop_loss_pct))
                
                logger.info(f"Set TP: {strategy.take_profit_pct}, SL: {strategy.stop_loss_pct}")
                
            except Exception as e:
                logger.warning(f"Risk settings partial fail: {e}")

            # Execute
            test_btn = page.locator("button:has-text('Test Strategy')")
            
            try:
                await test_btn.wait_for(state="visible", timeout=5000)
            except:
                pass
                
            logger.info("Clicking 'Test Strategy'...")
            await test_btn.click()
            
            # Wait & Scrape
            # Increased timeout to 90s for slower lookbacks
            await page.wait_for_selector("text=Cumulative PnL", timeout=90000)
            await asyncio.sleep(2)
            
            # Build Detailed Indicators String
            ind_details = []
            for ind in strategy.indicators:
                ind_details.append(f"{ind.name} {ind.operator} {ind.threshold_value}")
            
            results = {
                "timestamp": datetime.now().isoformat(),
                "strategy_name": strategy.name,
                "direction": strategy.direction,
                "timeframe": timeframe,
                "lookback": lookback,
                "tp_pct": strategy.take_profit_pct,
                "sl_pct": strategy.stop_loss_pct,
                "indicators_detail": " | ".join(ind_details),
                "status": "SUCCESS"
            }
            
            metrics_map = {
                "Total Trades": "total_trades",
                "Cumulative PnL": "cumulative_pnl",
                "Max Drawdown": "max_drawdown",
                "Avg Trade Duration": "avg_trade_duration",
                "Trades Won": "win_rate", 
                "Avg Win Trade": "avg_win_trade",
                "Profit Ratio": "profit_ratio",
                "Sharpe Ratio": "sharpe_ratio"
            }

            for label, key in metrics_map.items():
                try:
                    el = page.locator(f"//*[contains(text(), '{label}')]/following-sibling::*[1]").first
                    val = await el.inner_text()
                    results[key] = val
                except:
                    results[key] = "0"
            
            # Clean data for CSV
            try:
                results["net_profit"] = float(results.get("cumulative_pnl", "0").replace("%","").replace(",",""))
                results["trade_count"] = int(results.get("total_trades", "0"))
                raw_win_rate = results.get("win_rate", "0")
                if "(" in raw_win_rate:
                    import re
                    match = re.search(r'\((\d+\.?\d*)%\)', raw_win_rate)
                    if match:
                        results["win_rate"] = match.group(1) # "60.00"
                else:
                    results["win_rate"] = raw_win_rate.replace("%", "")
                    
            except Exception as e:
                logger.warning(f"Data cleaning warning: {e}")
                pass
                
            return results

        except Exception as e:
            logger.error(f"Run Error: {e}")
            return {"strategy_name": strategy.name, "status": "ERROR", "error": str(e)}
