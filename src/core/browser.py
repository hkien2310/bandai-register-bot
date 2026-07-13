import shutil
import time
import tempfile
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page
import src.config as config
from src.utils.logger import get_logger

log = get_logger("browser")

class BrowserInstance:
    def __init__(self, worker_id: int, proxy: dict | None = None):
        self.worker_id = worker_id
        self.proxy = proxy
        self.playwright = None
        self.context = None
        self.profile_dir = Path(tempfile.gettempdir()) / f"namco_browser_worker_{worker_id}"

    async def start(self) -> Page:
        """Khởi động Cloak Browser với proxy và profile tạm thời."""
        self.cleanup_profile_dir()
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.playwright = await async_playwright().start()

        # Thêm instance vào ACTIVE_BROWSERS để cho phép GUI đóng khẩn cấp khi người dùng bấm Stop
        if not hasattr(config, "ACTIVE_BROWSERS"):
            config.ACTIVE_BROWSERS = []
        config.ACTIVE_BROWSERS.append(self)

        # Cấu hình proxy cho Playwright — phải truyền đủ server + username + password
        launch_args = {}
        if self.proxy:
            playwright_proxy = {
                "server": self.proxy["server"],
            }
            if "username" in self.proxy:
                playwright_proxy["username"] = self.proxy["username"]
            if "password" in self.proxy:
                playwright_proxy["password"] = self.proxy["password"]
            launch_args["proxy"] = playwright_proxy
            log.info(f"Khởi động trình duyệt với proxy: {self.proxy['server']} | user={self.proxy.get('username', 'none')}")
        else:
            log.info("Khởi động trình duyệt không dùng proxy")

        executable_path = config.BROWSER_PATH if config.BROWSER_PATH else None
        log.info(f"Profile dir: {self.profile_dir}")

        base_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--incognito",
            "--inprivate"
        ]

        self.browser = None
        if executable_path:
            log.info(f"Dùng trình duyệt tùy chỉnh: {executable_path}")
            self.browser = await self.playwright.chromium.launch(
                executable_path=executable_path,
                headless=config.HEADLESS,
                args=base_args,
                **launch_args
            )
        else:
            # Thử Chrome trước trên mọi hệ điều hành, Edge làm dự phòng
            channels_to_try = ["chrome", "msedge"]
            
            for channel in channels_to_try:
                try:
                    log.info(f"Đang thử khởi động với trình duyệt: {channel}")
                    
                    self.browser = await self.playwright.chromium.launch(
                        channel=channel,
                        headless=config.HEADLESS,
                        args=base_args,
                        **launch_args
                    )
                    log.info(f"✅ Khởi động thành công với: {channel}")
                    break
                except Exception as e:
                    log.warning(f"⚠️ Không thể khởi động bằng {channel}: {e}")
            
            if not self.browser:
                raise Exception("Không tìm thấy Chrome hay Edge trên máy! Vui lòng cài đặt ít nhất một trong hai.")

        self.context = await self.browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1280, "height": 800}
        )

        page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        # Đặt timeout mặc định 90s cho môi trường proxy chậm
        page.set_default_timeout(90000)
        page.set_default_navigation_timeout(90000)

        # CHẾ ĐỘ TIẾT KIỆM BĂNG THÔNG: Chặn tải ảnh, video, font chữ
        async def block_heavy_resources(route):
            try:
                if route.request.resource_type in ["image", "media", "font"]:
                    await route.abort()
                else:
                    await route.continue_()
            except Exception:
                pass
        
        await self.context.route("**/*", block_heavy_resources)
        log.info("✅ Đã bật chế độ tiết kiệm băng thông (chặn ảnh/video/font) cho toàn bộ trình duyệt")

        # THEO DÕI DATA SỬ DỤNG
        self.total_bytes = 0
        async def on_request_finished(request):
            try:
                sizes = await request.sizes()
                if sizes:
                    self.total_bytes += sizes.get("requestBodySize", 0)
                    self.total_bytes += sizes.get("requestHeadersSize", 0)
                    self.total_bytes += sizes.get("responseBodySize", 0)
                    self.total_bytes += sizes.get("responseHeadersSize", 0)
            except Exception:
                pass
                
        self.context.on("requestfinished", on_request_finished)

        # Thiết lập Virtual WebAuthn Authenticator để chặn popup Bluetooth/USB Passkey của Chrome
        try:
            cdp = await self.context.new_cdp_session(page)
            await cdp.send("WebAuthn.enable")
            await cdp.send("WebAuthn.addVirtualAuthenticator", {
                "options": {
                    "protocol": "ctap2",
                    "transport": "usb",
                    "hasResidentKey": True,
                    "hasUserVerification": True,
                    "isUserVerified": True,
                    "automaticPresenceSimulation": True,
                }
            })
            log.info("✅ Đã kích hoạt Virtual WebAuthn Authenticator.")
        except Exception as e:
            log.warning(f"⚠️ Không thể kích hoạt Virtual WebAuthn: {e}")

        return page

    def get_data_usage_mb(self) -> float:
        """Trả về dung lượng data đã sử dụng tính bằng MB."""
        return getattr(self, 'total_bytes', 0) / (1024 * 1024)

    async def close(self):
        """Đóng trình duyệt và xóa sạch toàn bộ data (profile dir)."""
        log.info(f"Đang đóng trình duyệt Worker {self.worker_id}...")

        if self.context:
            try:
                await asyncio.wait_for(self.context.close(), timeout=10.0)
            except Exception as e:
                log.warning(f"Lỗi khi đóng context: {e}")
            self.context = None

        if hasattr(self, 'browser') and self.browser:
            try:
                await asyncio.wait_for(self.browser.close(), timeout=10.0)
            except Exception as e:
                log.warning(f"Lỗi khi đóng browser: {e}")
            self.browser = None

        if self.playwright:
            try:
                await asyncio.wait_for(self.playwright.stop(), timeout=10.0)
            except Exception as e:
                log.warning(f"Lỗi khi stop playwright: {e}")
            self.playwright = None

        # Xóa khỏi ACTIVE_BROWSERS
        if hasattr(config, "ACTIVE_BROWSERS") and self in config.ACTIVE_BROWSERS:
            try:
                config.ACTIVE_BROWSERS.remove(self)
            except ValueError:
                pass

        self.cleanup_profile_dir()

    def cleanup_profile_dir(self):
        """Xóa sạch thư mục profile tạm thời của browser."""
        if self.profile_dir.exists():
            log.info(f"🧹 Xóa data browser tại: {self.profile_dir}")
            for attempt in range(5):
                try:
                    shutil.rmtree(self.profile_dir, ignore_errors=True)
                    if not self.profile_dir.exists():
                        log.info("✅ Xóa data browser thành công.")
                        break
                except Exception as e:
                    log.warning(f"Thử xóa lần {attempt+1} lỗi: {e}")
                time.sleep(1)

            if self.profile_dir.exists():
                try:
                    shutil.rmtree(self.profile_dir)
                    log.info("✅ Cưỡng chế xóa data browser thành công.")
                except Exception as e:
                    log.error(f"❌ Không thể xóa thư mục profile: {e}")
