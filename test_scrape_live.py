import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import os

profile_path = os.path.join(os.getcwd(), "mexc_bot_profile")
chrome_options = Options()
chrome_options.add_argument(f"user-data-dir={profile_path}")

print("Connecting to browser...")
try:
    driver = webdriver.Chrome(options=chrome_options)
    driver.get("https://futures.mexc.com/exchange/LTC_USDT")
    time.sleep(5)
    
    script = """
    let elements = Array.from(document.querySelectorAll('tr, .row, [role="row"]'));
    return elements.map(el => {
        let text = el.innerText || "";
        return text;
    }).filter(t => t.toUpperCase().includes('LTC'));
    """
    
    rows = driver.execute_script(script)
    print(f"Found {len(rows)} rows with 'LTC'")
    for i, r in enumerate(rows):
        print(f"--- ROW {i} ---")
        print(r)
        
    driver.quit()
except Exception as e:
    print(f"Error: {e}")
