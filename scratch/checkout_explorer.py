from playwright.sync_api import sync_playwright
import time
import json

def explore():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()
        
        print("1. Go to product page")
        page.goto("https://parks2.bandainamco-am.co.jp/category/EL/ECCL00000036_20260711_022.html")
        page.wait_for_timeout(2000)
        
        # Click login link
        print("2. Looking for login")
        login_btn = page.query_selector("a:has-text('ログイン')")
        if login_btn:
            login_btn.click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)
            print(f"Current URL after clicking login: {page.url}")
            
            # Fill BNID and Password
            # Assuming standard BNID login form
            print("3. Filling login form")
            try:
                page.fill("input[type='email'], input[name='mail']", "a.t.t.j.41@gmail.com")
                page.fill("input[type='password'], input[name='pw']", "Namco2025!")
                # Click login submit
                page.click("button:has-text('ログイン'), button:has-text('Login'), input[type='submit'][value='ログイン']")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(5000)
                print(f"Logged in. URL is now: {page.url}")
            except Exception as e:
                print(f"Login failed: {e}")
        else:
            print("Already logged in or login button not found")

        # Now go back to product page
        page.goto("https://parks2.bandainamco-am.co.jp/category/EL/ECCL00000036_20260711_022.html")
        page.wait_for_timeout(3000)
        
        # Select first option if select exists
        print("4. Selecting option")
        try:
            selects = page.query_selector_all("select")
            if selects:
                opts = selects[0].query_selector_all("option")
                if len(opts) > 1:
                    val = opts[1].get_attribute("value")
                    selects[0].select_option(val)
                    print(f"Selected {val}")
        except Exception as e:
            print(e)
            
        page.wait_for_timeout(1000)
        
        print("5. Add to Cart")
        try:
            cart_btn = page.locator("button:has-text('カートに入れる'), a:has-text('カートに入れる'), input[value='カートに入れる']")
            if cart_btn.count() > 0:
                cart_btn.first.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(3000)
            else:
                print("Cart button not found")
        except Exception as e:
            print(e)
            
        print("6. Proceeding to checkout")
        try:
            # Maybe we are at /cart_index.html now. Find proceed to checkout button
            checkout_btn = page.locator("a:has-text('レジへ進む'), button:has-text('レジへ進む'), input[value='レジへ進む']")
            if checkout_btn.count() > 0:
                checkout_btn.first.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(4000)
            else:
                print("Proceed button not found, maybe going directly to URL")
                page.goto("https://parks2.bandainamco-am.co.jp/cart_pre.html")
                page.wait_for_timeout(4000)
        except Exception as e:
            print(e)
            
        print(f"Checkout URL: {page.url}")
        with open("scratch/checkout_form.html", "w", encoding="utf-8") as f:
            f.write(page.content())
            
        print("Extracting input names:")
        inputs = page.query_selector_all("input, select, textarea")
        fields = []
        for inp in inputs:
            name = inp.get_attribute("name")
            typ = inp.get_attribute("type")
            if name:
                fields.append({"name": name, "type": typ})
        
        with open("scratch/checkout_fields.json", "w", encoding="utf-8") as f:
            json.dump(fields, f, indent=2)

if __name__ == "__main__":
    explore()
