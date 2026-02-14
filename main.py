import asyncio
import logging
from browser_manager import browser_manager
from strategy_generator import StrategyGenerator
from backtest_runner import BacktestRunner
from analyzer import Analyzer
from config import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

async def run_batch_cycle(strategy_gen, runner, analyzer, page):
    logger.info("--- Starting New Batch ---")
    strategies = await strategy_gen.generate_strategy_batch(batch_size=1)
    
    for strategy in strategies:
        logger.info("Refreshing page to clear state...")
        try:
            await page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(5)
            
            # Set a hard timeout for each run (e.g., 5 minutes)
            # If it hangs, we raise TimeoutError and restart browser
            result = await asyncio.wait_for(
                runner.run_strategy(strategy), 
                timeout=300  # 5 minutes
            )
            
            analyzer.process_result(result)
            
        except asyncio.TimeoutError:
            logger.error("Strategy execution TIMED OUT (Hanged). Restarting browser...")
            raise RuntimeError("Browser Hang Detected")
        except Exception as e:
            logger.error(f"Strategy execution failed: {e}")
            
    logger.info("Batch finished. Waiting 10s...")
    await asyncio.sleep(10)

async def main():
    logger.info("Starting Hyblock Backtest Bot v3 (Resilient)...")
    
    analyzer = Analyzer()
    strategy_gen = StrategyGenerator()
    runner = BacktestRunner(browser_manager)
    
    while True:
        try:
            # 1. Setup & Login
            page = await browser_manager.setup_browser(headless=config.HEADLESS_MODE)
            await browser_manager.ensure_login(config.HYBLOCK_TARGET_URL)
            
            # 2. Run Batches until crash
            while True:
                await run_batch_cycle(strategy_gen, runner, analyzer, page)

        except RuntimeError as e:
            logger.warning(f"Recoverable Error: {e}. Restarting session...")
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            break
        except Exception as e:
            logger.critical(f"Critical Crash: {e}. Retrying in 30s...")
            await asyncio.sleep(30)
        finally:
            await browser_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
