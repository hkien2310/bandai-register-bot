import time
import asyncio
import re
from playwright.async_api import BrowserContext, Page
from src.utils.logger import get_logger
import src.config as config

log = get_logger("email_reader_web")

def _extract_otp(text: str) -> str | None:
    patterns = [
        r"認証コード[:\s\n**]+(\d{6})",
        r"verification code[:\s\n**]+(\d{6})",
        r"confirmation code[:\s\n**]+(\d{6})",
        r"your code[:\s\n**]+(\d{6})",
        r"\b(\d{6})\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None

async def safe_wait(page: Page, ms: int) -> bool:
    """Waits for ms milliseconds but checks STOP_FLAG every second. Returns False if stopped."""
    import src.config as config
    end_time = time.time() + ms / 1000.0
    while time.time() < end_time:
        if getattr(config, "STOP_FLAG", False):
            return False
        await page.wait_for_timeout(min(1000, max(1, int((end_time - time.time()) * 1000))))
    return True

async def safe_wait_for_selector(page: Page, selector: str, timeout: int = 30000) -> bool:
    """Waits for a selector in small chunks, checking STOP_FLAG."""
    import src.config as config
    end_time = time.time() + timeout / 1000.0
    while time.time() < end_time:
        if getattr(config, "STOP_FLAG", False):
            return False
        try:
            # wait 1000ms at a time
            await page.wait_for_selector(selector, timeout=1000)
            return True
        except:
            pass
    return False

async def prepare_outlook_tab(context: BrowserContext, target_email: str, target_password: str) -> Page | None:
    log.info(f"[{target_email}] Preparing Outlook tab (Pre-login)...")
    
    mail_page = None
    try:
        # Sử dụng window.open từ trang hiện tại để đảm bảo mở tab mới CÙNG một cửa sổ ẩn danh
        if context.pages:
            base_page = context.pages[0]
            async with context.expect_page() as page_info:
                await base_page.evaluate("window.open('https://login.live.com/', '_blank')")
            mail_page = await page_info.value
        else:
            mail_page = await context.new_page()
            await mail_page.goto("https://login.live.com/")
        
        next_btn_sel = "input[id='idSIButton9'], button[type='submit'], button[data-testid='primaryButton']"        # Check if we need to login or if we are at "Pick an account" screen
        is_login = False
        try:
            # Chờ ngắn 10s để xem có ra form email không
            if await safe_wait_for_selector(mail_page, "input[type='email'], input[name='loginfmt']", timeout=10000):
                is_login = True
            else:
                raise Exception("Not found")
        except:
            # Nếu không thấy form email, thử tìm nút "Use another account"
            try:
                other_acc = mail_page.locator("#otherTile, #otherTileText").first
                if await other_acc.is_visible(timeout=2000):
                    await other_acc.click()
                    if await safe_wait_for_selector(mail_page, "input[type='email'], input[name='loginfmt']", timeout=10000):
                        is_login = True
            except:
                is_login = False
        
        import src.config as config
        if getattr(config, "STOP_FLAG", False):
            return None
            
        if is_login:
            # 2. Fill email
            await mail_page.fill("input[type='email'], input[name='loginfmt']", target_email)
            await mail_page.locator(next_btn_sel).first.click()
            if not await safe_wait(mail_page, 2000): return None
            
            # 3. Fill password
            if not await safe_wait_for_selector(mail_page, "input[type='password'], input[name='passwd']", timeout=60000):
                if getattr(config, "STOP_FLAG", False): return None
            await mail_page.fill("input[type='password'], input[name='passwd']", target_password)
            await mail_page.locator(next_btn_sel).first.click()
            if not await safe_wait(mail_page, 3000): return None
            
            # 4. Xử lý các màn hình trung gian (Đòi thêm mail xác thực, Cập nhật bảo mật, Stay signed in...)
            for _ in range(4):
                if getattr(config, "STOP_FLAG", False): return None
                try:
                    # Nút bỏ qua (Skip for now, Cancel, No thanks)
                    skip_sel = "a[id='iCancel'], input[id='iCancel'], button[id='iCancel'], a[id='btnAskLater'], button[id='btnAskLater'], a[id='iShowSkip']"
                    if await mail_page.locator(skip_sel).count() > 0:
                        btn = mail_page.locator(skip_sel).first
                        if await btn.is_visible():
                            log.info(f"[{target_email}] Bấm nút Skip/Cancel màn hình xác thực...")
                            await btn.click()
                            if not await safe_wait(mail_page, 2000): return None
                            continue

                    # Nút tiếp tục (Stay signed in, Next)
                    next_sel = "input[id='idSIButton9'], button[type='submit'], button[data-testid='primaryButton']"
                    if await mail_page.locator(next_sel).count() > 0:
                        btn = mail_page.locator(next_sel).first
                        if await btn.is_visible():
                            log.info(f"[{target_email}] Bấm nút Tiếp tục/Stay signed in...")
                            await btn.click()
                            if not await safe_wait(mail_page, 2000): return None
                            continue
                except:
                    pass
                if not await safe_wait(mail_page, 1500): return None
                
        # 4. Navigate directly to Outlook mail (kích hoạt mailbox)
        log.info(f"[{target_email}] Navigating to Outlook Mail to initialize mailbox...")
        await mail_page.goto("https://outlook.live.com/mail/")
        
        # Wait for the long loading screen to finish (mailbox initialization)
        log.info(f"[{target_email}] Waiting for Outlook loading screen to finish...")
        try:
            # Đợi một phần tử đặc trưng của inbox hiển thị (thường là thanh tìm kiếm hoặc danh sách email)
            if not await safe_wait_for_selector(mail_page, "input#topSearchInput, div[aria-label='Message list'], div[role='main']", timeout=30000):
                if getattr(config, "STOP_FLAG", False): return None
        except:
            pass
            
        # Thêm một chút delay cứng để server MS "thở" và sẵn sàng nhận mail
        if not await safe_wait(mail_page, 8000): return None
        
        return mail_page
    except Exception as e:
        log.error(f"❌ Error preparing Outlook tab for {target_email}: {e}")
        await mail_page.close()
        return None

async def get_bandai_namco_otp_web(
    context: BrowserContext,
    since_ts: float,
    timeout: int,
    poll_interval: int,
    target_email: str,
    target_password: str,
    mail_page: Page | None = None
) -> str | None:
    log.info(f"⏳ Waiting for OTP (Web) | Target: {target_email} | Timeout: {timeout}s")
    
    close_page = False
    if not mail_page:
        mail_page = await prepare_outlook_tab(context, target_email, target_password)
        close_page = True
        
    if not mail_page:
        return None

    try:
        await mail_page.bring_to_front()
        
        deadline = time.time() + timeout
        while time.time() < deadline:
            if getattr(config, "STOP_FLAG", False):
                log.info(f"🛑 Bị dừng ép buộc trong lúc chờ OTP của {target_email}!")
                return None
                
            try:
                loc = mail_page.locator("text=/Bandai|バンダイナムコ|banapassport/i").first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click()
                    await mail_page.wait_for_timeout(2000) # wait for reading pane
                    
                    body_text = await mail_page.evaluate("document.body.innerText")
                    otp = _extract_otp(body_text)
                    if otp:
                        log.info(f"✅ Found Bandai Namco ID OTP (Web) = {otp}")
                        return otp
            except Exception as e:
                # Ignore transient errors like node detached
                pass
                
            await mail_page.wait_for_timeout(poll_interval * 1000)
            
        log.warning(f"⏰ Timeout {timeout}s — No OTP found for {target_email} via Web")
        return None
        
    except Exception as e:
        log.error(f"❌ Error in Web Email Reader for {target_email}: {e}")
        return None
    finally:
        if close_page and mail_page:
            await mail_page.close()
