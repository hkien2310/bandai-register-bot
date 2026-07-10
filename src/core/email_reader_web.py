import time
import asyncio
import re
from playwright.async_api import BrowserContext, Page
from src.utils.logger import get_logger

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

async def prepare_outlook_tab(context: BrowserContext, target_email: str, target_password: str) -> Page | None:
    log.info(f"[{target_email}] Preparing Outlook tab (Pre-login)...")
    mail_page = await context.new_page()
    try:
        # 1. Navigate to login.live.com
        await mail_page.goto("https://login.live.com/")
        
        next_btn_sel = "input[id='idSIButton9'], button[type='submit'], button[data-testid='primaryButton']"
        
        # Check if we need to login or if we are at "Pick an account" screen
        is_login = False
        try:
            # Chờ ngắn 10s để xem có ra form email không
            await mail_page.wait_for_selector("input[type='email'], input[name='loginfmt']", timeout=10000)
            is_login = True
        except:
            # Nếu không thấy form email, thử tìm nút "Use another account"
            try:
                other_acc = mail_page.locator("#otherTile, #otherTileText").first
                if await other_acc.is_visible(timeout=2000):
                    await other_acc.click()
                    await mail_page.wait_for_selector("input[type='email'], input[name='loginfmt']", timeout=10000)
                    is_login = True
            except:
                is_login = False
        
            
        if is_login:
            # 2. Fill email
            await mail_page.fill("input[type='email'], input[name='loginfmt']", target_email)
            await mail_page.locator(next_btn_sel).first.click()
            await mail_page.wait_for_timeout(2000)
            
            # 3. Fill password
            await mail_page.wait_for_selector("input[type='password'], input[name='passwd']", timeout=60000)
            await mail_page.fill("input[type='password'], input[name='passwd']", target_password)
            await mail_page.locator(next_btn_sel).first.click()
            await mail_page.wait_for_timeout(3000)
            
            # 4. Xử lý các màn hình trung gian (Đòi thêm mail xác thực, Cập nhật bảo mật, Stay signed in...)
            for _ in range(4):
                try:
                    # Nút bỏ qua (Skip for now, Cancel, No thanks)
                    skip_sel = "a[id='iCancel'], input[id='iCancel'], button[id='iCancel'], a[id='btnAskLater'], button[id='btnAskLater'], a[id='iShowSkip']"
                    if await mail_page.locator(skip_sel).count() > 0:
                        btn = mail_page.locator(skip_sel).first
                        if await btn.is_visible():
                            log.info(f"[{target_email}] Bấm nút Skip/Cancel màn hình xác thực...")
                            await btn.click()
                            await mail_page.wait_for_timeout(2000)
                            continue

                    # Nút tiếp tục (Stay signed in, Next)
                    if await mail_page.locator(next_btn_sel).count() > 0:
                        btn = mail_page.locator(next_btn_sel).first
                        if await btn.is_visible():
                            log.info(f"[{target_email}] Bấm nút Next/Stay Signed In...")
                            await btn.click()
                            await mail_page.wait_for_timeout(2000)
                            continue
                except:
                    pass
                await mail_page.wait_for_timeout(1000)
                
        # 4. Navigate directly to Outlook mail (kích hoạt mailbox)
        log.info(f"[{target_email}] Navigating to Outlook Mail to initialize mailbox...")
        await mail_page.goto("https://outlook.live.com/mail/")
        
        # Wait for the long loading screen to finish (mailbox initialization)
        log.info(f"[{target_email}] Waiting for Outlook loading screen to finish...")
        try:
            # Đợi một phần tử đặc trưng của inbox hiển thị (thường là thanh tìm kiếm hoặc danh sách email)
            await mail_page.wait_for_selector("input#topSearchInput, div[aria-label='Message list'], div[role='main']", timeout=30000)
        except:
            pass
            
        # Thêm một chút delay cứng để server MS "thở" và sẵn sàng nhận mail
        await mail_page.wait_for_timeout(8000)
        
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
