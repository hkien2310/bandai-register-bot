from playwright.sync_api import sync_playwright
import json
from datetime import datetime
import os

os.makedirs("scratch", exist_ok=True)

def run():
    logs = []
    log_file = "scratch/network_log.json"
    
    with sync_playwright() as p:
        # Cấu hình browser "cloak" để tránh bị chặn chặn bot cơ bản
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--start-maximized'
            ]
        )
        context = browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Thêm script để ẩn dấu hiệu webdriver
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """)
        
        page = context.new_page()
        
        def handle_response(response):
            # Chỉ bắt các request dạng XHR / Fetch (thường là gọi API)
            if response.request.resource_type in ["xhr", "fetch"]:
                try:
                    url = response.url
                    # Bỏ qua các URL tracking/analytics nếu cần (ở đây cứ bắt hết)
                    if "google-analytics.com" in url or "googletagmanager.com" in url:
                        return

                    method = response.request.method
                    status = response.status
                    post_data = response.request.post_data
                    
                    resp_json = None
                    try:
                        # Chỉ parse JSON nếu server trả về content-type là json
                        if "application/json" in response.headers.get("content-type", ""):
                            resp_json = response.json()
                    except:
                        pass
                        
                    log_entry = {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "method": method,
                        "url": url,
                        "status": status,
                        "post_data": post_data,
                        "response_json": resp_json
                    }
                    print(f"[{method}] {status} - {url}")
                    logs.append(log_entry)
                    
                    with open(log_file, "w", encoding="utf-8") as f:
                        json.dump(logs, f, ensure_ascii=False, indent=2)
                        
                except Exception as e:
                    pass

        page.on("response", handle_response)
        
        print("="*60)
        print("🌐 TRÌNH DUYỆT ĐANG MỞ!")
        print("👉 Hãy truy cập trang sản phẩm của Bandai Namco Parks.")
        print("👉 Thử thực hiện luồng: Xem sản phẩm -> Chọn Option -> Add To Cart.")
        print(f"🔍 Toàn bộ API calls sẽ được record lại tại: {log_file}")
        print("❌ Sau khi test xong, hãy tự ĐÓNG cửa sổ trình duyệt để kết thúc script.")
        print("="*60)
        
        try:
            # Mở sẵn trang chủ
            page.goto("https://parks2.bandainamco-am.co.jp/")
            # Chờ cho đến khi user đóng tab/cửa sổ
            page.wait_for_event("close", timeout=0)
        except Exception:
            print("\nTrình duyệt đã được đóng. Script kết thúc.")

if __name__ == "__main__":
    run()
