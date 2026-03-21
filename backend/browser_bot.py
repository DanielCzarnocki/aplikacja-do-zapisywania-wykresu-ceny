import time
import logging
import threading
import requests
import getpass
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("bot_debug.log"),
                        logging.StreamHandler()
                    ])
logger = logging.getLogger("BrowserBot")

class BrowserBot:
    def __init__(self):
        self.driver = None
        self.is_running = False
        self.last_processed_signal_time = 0
        self.last_signal_text = ""
        
    def start_browser(self):
        logger.info("Starting Chrome with dedicated bot profile...")
        import os
        # Create a dedicated directory in the project for the bot's Chrome Profile
        user_data_dir = os.path.abspath("mexc_bot_profile")
        os.makedirs(user_data_dir, exist_ok=True)
        
        chrome_options = Options()
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        chrome_options.add_argument("--profile-directory=Default")
        # Optimization options
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--window-size=1200,800")
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.get("https://futures.mexc.com/exchange/LTC_USDT")
            logger.info("Browser opened. Please verify you are logged in.")
            
            # Wait for the page to load and market order tab to be visible
            time.sleep(5)
            self._ensure_market_tab()
            
            self.is_running = True
            threading.Thread(target=self._loop, daemon=True).start()
        except Exception as e:
            logger.error(f"Failed to start browser: {e}")
            logger.info("Make sure all other Chrome windows are closed!")

    def _ensure_market_tab(self):
        """Ensures the Market (Rynkowe) tab is selected for quick execution."""
        try:
            # Note: Selectors need to be fine-tuned based on actual MEXC DOM
            # Looking for elements that contain "Market" or "Rynkowe"
            market_tab = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Market') or contains(text(), 'Rynkowe')]"))
            )
            market_tab.click()
            logger.info("Selected Market order tab.")
        except Exception as e:
            logger.warning("Could not auto-select Market tab. Make sure it's selected manually!")

    def execute_trade(self, action, amount_ltc):
        """Action can be 'LONG', 'SHORT', 'CLOSE_LONG', 'CLOSE_SHORT'"""
        if not self.driver:
            return
            
        logger.info(f"Executing {action} for {amount_ltc} LTC")
        try:
            # 0. Dismiss any stuck modals before doing anything
            self.driver.execute_script("""
            // 1. Tick "Don't show again" / "Koniec porad na dziś" checkboxes
            let labels = Array.from(document.querySelectorAll('label, span, div'));
            let dntShowLabel = labels.find(l => {
                let text = l.innerText.toLowerCase();
                return text.includes('koniec porad') || text.includes('nie pokazuj') || text.includes("don't show");
            });
            if (dntShowLabel) {
                 let cb = dntShowLabel.querySelector('input[type="checkbox"]') || dntShowLabel.previousElementSibling;
                 if (cb && !cb.checked) cb.click();
                 else dntShowLabel.click(); // sometimes clicking the label itself checks the box
            }

            // 2. Kill dialogue boxes
            let modals = document.querySelectorAll('.ant-modal-wrap, .ant-modal, [role="dialog"], [class*="Modal_modal__"]'); 
            modals.forEach(m => {
                if (window.getComputedStyle(m).display !== 'none') {
                    let btns = Array.from(m.querySelectorAll('button'));
                    let confirm = btns.find(b => {
                        let up = b.innerText.toUpperCase();
                        return b.classList.contains('ant-btn-primary') || up.includes('CONFIRM') || up.includes('POTWIERDŹ') || up.includes('OK') || up.includes('ZROZUMIAŁEM');
                    });
                    if(confirm) {
                        confirm.click();
                        return;
                    }
                    
                    let closeBtn = m.querySelector('.ant-modal-close, [aria-label*="Close"], [aria-label*="Zamknij"], .close');
                    if(closeBtn) {
                        closeBtn.click();
                        return;
                    }
                    
                    // Fallback to top-right X SVGs or icons
                    let iconBtn = Array.from(m.querySelectorAll('svg, i')).find(s => {
                        let cls = (s.getAttribute('class') || '').toLowerCase();
                        return cls.includes('close') || cls.includes('cancel');
                    });
                    if(iconBtn) {
                        if (iconBtn.parentElement.tagName === 'BUTTON' || iconBtn.parentElement.tagName === 'DIV') {
                            iconBtn.parentElement.click();
                        } else {
                            iconBtn.click();
                        }
                    }
                }
            });
            """)
            time.sleep(0.5) # Give it a moment to dismiss

            if action == "TEST_POPUP":
                logger.info('Test Zamykania Popupów zakończony pomyslnie.')
                return

            if action in ["LONG", "SHORT"]:
                # 1. Enter Amount via JS (robust)
                script_find_input = """
                let inputs = Array.from(document.querySelectorAll('input'));
                let visible = inputs.filter(i => i.offsetWidth > 0 && i.offsetHeight > 0 && !i.disabled && !i.readOnly && (i.type === 'text' || i.type === 'number'));
                return visible.length > 0 ? visible[visible.length - 1] : null;
                """
                amount_input = self.driver.execute_script(script_find_input)
                
                if amount_input:
                    # Clear input safely
                    amount_input.send_keys(Keys.CONTROL, 'a')
                    amount_input.send_keys(Keys.DELETE)
                    amount_input.clear()
                    
                    # Prevent 10.0 being typed as 100
                    try:
                        f_amt = float(amount_ltc)
                        final_amt = str(int(f_amt)) if f_amt.is_integer() else str(f_amt)
                    except:
                        final_amt = str(amount_ltc)
                        
                    amount_input.send_keys(final_amt)
                else:
                    logger.error("Could not find amount input.")
                    return
                
                # Wait 1 second as requested
                time.sleep(1)
                
                # 3. Click Button
                script_find_btn = """
                let action = arguments[0];
                // First try data-testids as they are most reliable
                if (action === 'LONG') {
                    let btn = document.querySelector('[data-testid="contract-trade-open-long-btn"]');
                    if (btn) return btn;
                } else if (action === 'SHORT') {
                    let btn = document.querySelector('[data-testid="contract-trade-open-short-btn"]');
                    if (btn) return btn;
                }
                
                // Fallback to strict text matching
                let btns = Array.from(document.querySelectorAll('button'));
                return btns.find(b => {
                    if (b.offsetWidth === 0) return false;
                    let t = b.innerText.toLowerCase();
                    let isLong = t.includes('long') || t.includes('dług') || t.includes('dlug');
                    let isShort = t.includes('short') || t.includes('krót') || t.includes('krot');
                    let isOpen = t.includes('open') || t.includes('otwórz') || t.includes('otworz');
                    
                    if (action === 'LONG' && isLong && isOpen) return true;
                    if (action === 'SHORT' && isShort && isOpen) return true;
                    return false;
                });
                """
                btn = self.driver.execute_script(script_find_btn, action)
                
                if btn:
                    btn.click()
                    logger.info(f"Clicked {action} button after 1s wait.")
                else:
                    logger.error(f"Could not find {action} button.")
                
                
            elif action in ["CLOSE_LONG", "CLOSE_SHORT"]:
                # We need to find the specific "Flash Close" button for the correct position type.
                # To be robust against structure, we use a JS snippet similar to our scraper.
                script = """
                let rows = Array.from(document.querySelectorAll('tr, .row, [role="row"]'));
                let targetType = arguments[0]; // 'LONG' or 'SHORT'
                
                for(let row of rows) {
                    let text = window.getComputedStyle(row).display !== 'none' ? row.innerText.toUpperCase() : '';
                    if (!text.includes('LTC')) continue;
                    
                    let isLongTarget = targetType === 'LONG';
                    let matchesTarget = false;
                    
                    if (isLongTarget && (text.includes('LONG') || text.includes('DŁUG') || text.includes('DLUG'))) {
                        matchesTarget = true;
                    } else if (!isLongTarget && (text.includes('SHORT') || text.includes('KRÓT') || text.includes('KROT'))) {
                        matchesTarget = true;
                    }
                    
                    if(matchesTarget) {
                        // Find flash close button inside this row
                        let btns = Array.from(row.querySelectorAll('button'));
                        let flashBtn = btns.find(b => {
                            let upper = b.innerText.toUpperCase();
                            return upper.includes('FLASH') || upper.includes('SZYBKIE') || upper.includes('BŁYSK') || upper.includes('BLYSK');
                        });
                        if(flashBtn) {
                            flashBtn.click();
                            return true;
                        }
                    }
                }
                return false;
                """
                
                target_str = "LONG" if action == "CLOSE_LONG" else "SHORT"
                clicked = self.driver.execute_script(script, target_str)
                
                if clicked:
                    time.sleep(0.5)
                    # Handle confirmation dialog if any pops up
                    try:
                        confirm = self.driver.find_element(By.XPATH, "//button[contains(., 'Confirm') or contains(., 'Potwierdź')]")
                        confirm.click()
                        logger.info(f"Confirmed Flash Close for {target_str}.")
                    except:
                        logger.info(f"Executed Flash Close for {target_str} (No confirm needed).")
                else:
                    logger.warning(f"Could not find Flash Close button for {target_str} position.")
                
        except Exception as e:
            logger.error(f"Error executing trade in DOM: {e}")

    def _loop(self):
        logger.info("Browser bot signal loop started.")
        while self.is_running:
            try:
                # Fetch current signal from local API
                res = requests.get("http://127.0.0.1:8000/api/current_candle", timeout=3)
                if res.status_code == 200:
                    data = res.json()
                    # AUTO SYNC TRADING
                    is_auto = data.get("is_auto_trading", False)
                    panel = data.get("panel", {})
                    
                    if is_auto and panel:
                        # 1. Get targets from strategy
                        target_long = float(panel.get("L_poz", 0))
                        target_short = float(panel.get("S_poz", 0))
                        
                        # 2. Get current real positions from last scrape
                        if hasattr(self, 'last_state'):
                            real_long = self.last_state.get("long_amount", 0.0)
                            real_short = self.last_state.get("short_amount", 0.0)
                            
                            # ---------- LONG SYNC ----------
                            diff_long = int(round(target_long - real_long))
                            if diff_long >= 1:
                                logger.info(f"[AUTO] Syncing Long: Strategy wants {target_long}, we have {real_long}. Opening {diff_long} LONG.")
                                self.execute_trade("LONG", diff_long)
                            elif target_long == 0 and real_long > 0:
                                logger.info(f"[AUTO] Syncing Long: Strategy wants 0. Closing Long.")
                                self.execute_trade("CLOSE_LONG", 0)
                                
                            # ---------- SHORT SYNC ----------
                            diff_short = int(round(target_short - real_short))
                            if diff_short >= 1:
                                logger.info(f"[AUTO] Syncing Short: Strategy wants {target_short}, we have {real_short}. Opening {diff_short} SHORT.")
                                self.execute_trade("SHORT", diff_short)
                            elif target_short == 0 and real_short > 0:
                                logger.info(f"[AUTO] Syncing Short: Strategy wants 0. Closing Short.")
                                self.execute_trade("CLOSE_SHORT", 0)
                                
                            # Prevent spamming the API too fast in auto mode if executing
                            if diff_long >= 1 or diff_short >= 1 or (target_long == 0 and real_long > 0) or (target_short == 0 and real_short > 0):
                                time.sleep(2) # Extra delay after action to let scrape catch up
                            
                # --- MANUAL TRADES ---
                try:
                    man_res = requests.get("http://127.0.0.1:8000/api/get_manual_commands", timeout=2)
                    if man_res.status_code == 200:
                        man_data = man_res.json()
                        cmds = man_data.get("commands", [])
                        for cmd in cmds:
                            action = cmd.get("action")
                            amount = cmd.get("amount", 0)
                            logger.info(f"Bot executing MANUAL TRADE: {action} {amount} LTC")
                            self.execute_trade(action, amount)
                except Exception as e:
                    pass


                            
                # --- WEB SCRAPING POSITIONS ---
                # Check every few seconds instead of every 1 second to reduce CPU UI lag
                current_t = time.time()
                if not hasattr(self, 'last_scrape') or current_t - self.last_scrape > 2:
                    self.last_scrape = current_t
                    self._scrape_and_send_positions()
                            
            except Exception as e:
                logger.error(f"Error in bot loop: {e}")
                
            time.sleep(1) # Check every 1 second

    def _scrape_and_send_positions(self):
        if not self.driver:
            return
        try:
            script = """
            try {
                let elements = Array.from(document.querySelectorAll('tr, .row, [role="row"]'));
                let rows = elements.filter(el => {
                    let text = el.innerText || "";
                    let upper = text.toUpperCase();
                    // Just look for LTC and LONG/SHORT or Polish DŁUG/KRÓT without space
                    if (upper.includes("LTC") && (upper.includes("LONG") || upper.includes("SHORT") || upper.includes("DŁUG") || upper.includes("DLUG") || upper.includes("KRÓT") || upper.includes("KROT"))) {
                        let lines = text.split('\\n').filter(l => l.trim().length > 0);
                        return lines.length >= 4;
                    }
                    return false;
                });
                
                rows.sort((a,b) => a.innerText.length - b.innerText.length);
                return rows.slice(0, 4).map(r => r.innerText);
            } catch(e) { return []; }
            """
            
            row_texts = self.driver.execute_script(script)
            
            with open("test_scrape.txt", "w", encoding="utf-8") as f:
                if row_texts:
                    f.write(f"Scraping active. Found {len(row_texts)} rows:\n")
                    for r in row_texts:
                        f.write(f"--- ROW ---\n{r}\n")
                else:
                    f.write("Scraping active. Found 0 rows.\n")
                    
            if row_texts:
                logger.info(f"Scraping active. Found {len(row_texts)} rows:")
                for r in row_texts:
                    logger.info(f"--- ROW ---\n{r}")
            
            state = {
                "long_amount": 0.0, "long_price": 0.0, "long_pnl": 0.0,
                "short_amount": 0.0, "short_price": 0.0, "short_pnl": 0.0
            }
            
            import re
            
            found_long = False
            found_short = False
            
            for text in row_texts:
                upper = text.upper()
                is_long = ("LONG" in upper or "DŁUG" in upper or "DLUG" in upper) and not found_long
                is_short = ("SHORT" in upper or "KRÓT" in upper or "KROT" in upper) and not found_short
                
                if not is_long and not is_short:
                    continue
                    
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                # Typically format for MEXC rows:
                # LTCUSDT
                # 20X Long
                # 1.500 (Size/Amount)
                # ...
                
                amount = 0.0
                price = 0.0
                pnl = 0.0
                
                # First pass: Look for explicit labels
                for line in lines:
                    up = line.upper()
                    nums = re.findall(r'-?\d+\.?\d*', line.replace(',', ''))
                    if nums and ('KONTRAKT' in up or 'CONT' in up or 'LTC' in up):
                        # The amount might be on the same line
                        amount = float(nums[0])
                        break
                
                def parse_float(s):
                    s = s.replace('\u200e', '').replace('\u200f', '').replace('\u200b', '')
                    s = s.replace(' ', '').replace('+', '')
                    s = s.replace(',', '')
                    try:
                        return float(s)
                    except:
                        return None
                        
                amount = 0.0
                price = 0.0
                pnl = 0.0

                for line in lines:
                    up = line.upper()
                    if 'KONTRAKT' in up or 'CONT' in up:
                        nums = re.findall(r'-?\d+[ \d]*[.,]?\d*', line)
                        parsed = []
                        for n in nums:
                            p = parse_float(n)
                            if p is not None: parsed.append(p)
                            
                        if len(parsed) >= 1:
                            amount = parsed[0]
                        if len(parsed) >= 2:
                            price = parsed[1]
                        break

                for line in reversed(lines):
                    if ('-' in line or '+' in line) and 'USDT' in line.upper() and '%' not in line:
                        pnl_nums = re.findall(r'[+-]\d+[ \d]*[.,]?\d*', line)
                        if pnl_nums:
                            val = parse_float(pnl_nums[0])
                            if val is not None:
                                pnl = val
                                break
                
                if is_long:
                    state["long_amount"] = amount
                    state["long_price"] = price
                    state["long_pnl"] = pnl
                    found_long = True
                elif is_short:
                    state["short_amount"] = amount
                    state["short_price"] = price
                    state["short_pnl"] = pnl
                    found_short = True
                    
            requests.post("http://127.0.0.1:8000/api/live_position", json=state, timeout=2)
            self.last_state = state
        except Exception as e:
            pass

# To keep it alive if run independently
if __name__ == "__main__":
    bot = BrowserBot()
    bot.start_browser()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping bot.")
        if bot.driver:
            bot.driver.quit()
