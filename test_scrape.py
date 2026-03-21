import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

print("Starting headless Chrome...")
user_data_dir = os.path.abspath("mexc_bot_profile")
chrome_options = Options()
chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
chrome_options.add_argument("--profile-directory=Default")
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--window-size=1920,1080")

try:
    driver = webdriver.Chrome(options=chrome_options)
    driver.get("https://futures.mexc.com/exchange/LTC_USDT")
    time.sleep(8)
    
    # Dump all text from elements that look like table rows or position containers
    script = """
    let els = document.querySelectorAll('.position-item, tr, [role="row"]');
    return Array.from(els).map(e => e.innerText).filter(t => t.toUpperCase().includes('LTC'));
    """
    res = driver.execute_script(script)
    print("Found rows with LTC:", res)
    
    # If nothing, dump the whole text
    if not res:
        print("Body text dump snippet:")
        print(driver.find_element(By.TAG_NAME, "body").text[:2000])
        
    driver.quit()
except Exception as e:
    print("Error:", e)
