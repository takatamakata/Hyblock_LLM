import asyncio
import os
import logging
from playwright.async_api import async_playwright, Page, BrowserContext, Browser
from config import config

logger = logging.getLogger(__name__)

class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def setup_browser(self, headless: bool = False) -> Page:
        self.playwright = await async_playwright().start()
        
        # Use a real user agent to prevent UI hiding
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        self.browser = await self.playwright.chromium.launch(
            headless=headless, 
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        
        context_args = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": user_agent
        }

        # Force new session if auth file missing
        if config.AUTH_FILE.exists():
            logger.info(f"Loading session from {config.AUTH_FILE}")
            self.context = await self.browser.new_context(
                storage_state=str(config.AUTH_FILE),
                **context_args
            )
        else:
            logger.info("Starting new session (no auth file found)")
            self.context = await self.browser.new_context(**context_args)

        self.page = await self.context.new_page()
        return self.page

    async def ensure_login(self, target_url: str = config.HYBLOCK_TARGET_URL):
        if not self.page:
            raise RuntimeError("Browser not initialized.")

        # If no auth file, go straight to login
        if not config.AUTH_FILE.exists():
            logger.info("No auth file. Going to Login Page...")
            await self.page.goto(config.HYBLOCK_LOGIN_URL)
        else:
            logger.info(f"Navigating to {target_url}...")
            await self.page.goto(target_url, wait_until="domcontentloaded")
            
        await asyncio.sleep(3) # Stabilization
        
        # ... Rest of the robust login check ...

        # --- ROBUST LOGIN CHECK ---
        # 1. Check URL for 'login'
        # 2. Check for presence of 'Login' or 'Sign In' buttons
        # 3. Check for 'Profile' or 'Logout' (indicators of success)
        
        is_login_url = "login" in self.page.url.lower()
        
        # Look for common login indicators
        login_button = self.page.locator("button:has-text('Login'), a:has-text('Login'), button:has-text('Sign In')")
        is_login_button_visible = await login_button.count() > 0 and await login_button.first.is_visible()
        
        if is_login_url or is_login_button_visible:
            logger.warning(">>> SESSION INVALID OR NOT LOGGED IN <<<")
            logger.info("Action Required: Please log in manually in the browser window.")
            
            # If we have an auth file that didn't work, maybe delete it?
            # For now, we just overwrite it after successful login.
            
            # Navigate to login if button clicked or just wait
            if is_login_button_visible and not is_login_url:
                logger.info("Clicking detected Login button...")
                try:
                    await login_button.first.click()
                except:
                    pass

            # Wait Loop
            while True:
                # Break condition: URL does not contain login AND Login button is GONE
                current_url = self.page.url.lower()
                login_btn_count = await self.page.locator("button:has-text('Login')").count()
                
                if "login" not in current_url and login_btn_count == 0:
                    break
                    
                logger.info("Waiting for user to log in...")
                await asyncio.sleep(3)
            
            logger.info("Login detected! Waiting for redirection...")
            await asyncio.sleep(5)
            
            # Save new session
            await self.context.storage_state(path=str(config.AUTH_FILE))
            logger.info(f"New session saved to {config.AUTH_FILE}")
            
            # Force navigation to target if not there
            if target_url not in self.page.url:
                await self.page.goto(target_url, wait_until="domcontentloaded")
            
            return True
        else:
            logger.info("User appears to be logged in (No login button found).")
            return True

    async def select_dropdown_option(self, trigger_label: str, option_text: str, index: int = None, open_only: bool = False):
        """
        Robust function to handle Hyblock Dropdowns.
        
        Args:
            index: 0-based index of the MuiAutocomplete-popupIndicator button.
            open_only: If True, only opens the dropdown without selecting an option.
        """
        try:
            logger.info(f"Interacting with dropdown '{trigger_label}' (Index: {index})...")
            
            # 1. Click the Dropdown Trigger
            if index is not None:
                # Match the JS Logic: document.querySelectorAll('.MuiAutocomplete-popupIndicator')[index]
                # We target the button specifically.
                buttons = self.page.locator(".MuiAutocomplete-popupIndicator")
                target_btn = buttons.nth(index)
                
                # Check visibility
                if await target_btn.count() == 0:
                    logger.warning(f"Button at index {index} not found. Trying generic combobox.")
                    target_btn = self.page.locator("[role='combobox']").nth(index)
                
                # Click to open
                await target_btn.click(force=True)
            else:
                # Fallback to label click
                await self.page.click(f"label:has-text('{trigger_label}')", force=True)
            
            # If we only wanted to open it (for multi-select flow), stop here.
            if open_only:
                # Wait for listbox to appear to ensure it's open
                await self.page.wait_for_selector("ul[role='listbox'], div[role='presentation']", state="visible", timeout=3000)
                return

            # 2. Wait for Options List
            await self.page.wait_for_selector("ul[role='listbox'], div[role='presentation']", state="visible", timeout=3000)

            # 3. Select Option
            if option_text and option_text.lower() != "none":
                # Look for li or div with role option containing the text
                # Using exact=False to be lenient, but has-text is robust
                option = self.page.locator(f"li[role='option']:has-text('{option_text}')").first
                
                if await option.count() == 0:
                    # Fallback: Checkbox label inside li
                    option = self.page.locator(f"li:has-text('{option_text}')").first
                
                await option.click(force=True)
                
                # Close check: If it's single select, listbox usually closes. 
                # If multi-select, it stays open. We assume single select here unless managed by caller.
                
        except Exception as e:
            logger.error(f"Dropdown error ({trigger_label}): {e}")
            await self.page.screenshot(path=f"error_dropdown_{trigger_label}.png")
            raise

    async def select_item_in_open_listbox(self, option_text: str):
        """
        Selects an item assuming the listbox is ALREADY open.
        """
        try:
            if not option_text or option_text.lower() == "none":
                return

            # Wait for the specific option to be visible
            option = self.page.locator(f"li[role='option']:has-text('{option_text}')").first
            
            # Fallback for virtualized lists or complex DOM
            if await option.count() == 0:
                 option = self.page.locator(f"li:has-text('{option_text}')").first
            
            # Scroll into view if needed (Hyblock list is long)
            await option.scroll_into_view_if_needed()
            
            # Force move mouse to option to trigger hover effects if any
            box = await option.bounding_box()
            if box:
                await self.page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
            
            await option.click(force=True)
            logger.info(f"Selected: {option_text}")
            
        except Exception as e:
            logger.error(f"Failed to select item '{option_text}': {e}")
            raise

    async def toggle_normalize(self):
        """Clicks 'Normalize' toggle if not active."""
        try:
            # Target the MUI Switch input directly
            # It usually has a class like 'MuiSwitch-input'
            # We want to ensure it's checked/true.
            
            # Locate the switch container or input
            switch_input = self.page.locator("input.MuiSwitch-input").first
            
            if await switch_input.count() > 0:
                is_checked = await switch_input.is_checked()
                if not is_checked:
                    # Click the parent span/div to toggle, as input might be hidden/overlayed
                    await switch_input.locator("..").click(force=True)
                    logger.info("Normalize toggle ENABLED.")
                else:
                    logger.info("Normalize already enabled.")
            else:
                # Fallback to text label click
                await self.page.click("text=Normalize", force=True)
                
        except Exception as e:
            logger.warning(f"Normalize toggle failed: {e}")

    async def close(self):
        if self.browser:
            await self.browser.close()

browser_manager = BrowserManager()
