import time
import random
import re
from playwright.async_api import Page
import src.config as config
from src.core.email_reader import get_bandai_namco_otp
from src.utils.logger import get_logger

log = get_logger("step3_bnid_register")


async def human_delay(page: Page, min_ms: int = 800, max_ms: int = 2000):
    """Delay ngẫu nhiên giả lập hành động người dùng."""
    delay = random.randint(min_ms, max_ms)
    log.debug(f"   [human delay] {delay}ms")
    await page.wait_for_timeout(delay)


async def run_step3(page: Page, email: str, password: str, birthday: str, has_bnid: bool = False, email_password: str = "", refresh_token: str = None, client_id: str = None) -> str:
    """
    Điền form Bandai Namco ID.
    Sau khi submit form, đợi nhận OTP từ catch-all email, điền OTP, và lấy User Code.
    
    Nếu has_bnid=True (account đã có BNID), chỉ đăng nhập và lấy User Code, KHÔNG cần đăng ký.
    
    Trả về BNID User Code.
    """
    # Mở tab chuẩn bị lấy email trước
    since_ts = time.time()
    
    mail_page = None
    is_outlook = email.lower().endswith(("@hotmail.com", "@outlook.com", "@live.com"))
    if is_outlook and email_password and not (refresh_token and client_id):
        from src.core.email_reader_web import prepare_outlook_tab
        mail_page = await prepare_outlook_tab(page.context, email, email_password)
        if mail_page:
            await page.bring_to_front()
    elif refresh_token and client_id:
        log.info(f"   Dùng DongVanFB API cho {email}. Bỏ qua bước mở tab web mail.")
    
    if has_bnid:
        log.info(f"--- THỰC HIỆN ĐĂNG NHẬP BANDAI NAMCO ID ({email}) ---")
        await page.wait_for_selector("input#mail, input[name='mail']", timeout=20000)
        await human_delay(page, 600, 1200)

        email_field = page.locator("input#mail, input[name='mail']")
        await email_field.fill(email)
        await human_delay(page, 400, 800)
        await email_field.blur()

        pass_field = page.locator("input#pass, input[name='pass']")
        await human_delay(page, 600, 1200)
        await pass_field.fill(password)
        await human_delay(page, 400, 800)
        await pass_field.blur()

        log.info("Submit form đăng nhập BNID...")
        await human_delay(page, 800, 1500)
        login_btn = await page.wait_for_selector("button#btn-idpw-login", timeout=60000)
        await login_btn.click()
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            pass

        # Xử lý các màn hình đồng ý điều khoản bổ sung nếu có khi login
        log.info("Kiểm tra màn hình chấp nhận điều khoản bổ sung khi đăng nhập...")
        for _ in range(3):
            await page.wait_for_timeout(1000)
            try:
                cbs = await page.query_selector_all("input[type='checkbox']")
                for cb in cbs:
                    await cb.evaluate("el => { if (!el.checked) el.click(); }")

                agree_btn = await page.query_selector("button#btn-agree-b, button#btn-accept-all")
                if agree_btn:
                    log.info("Phát hiện và click nút đồng ý điều khoản bổ sung...")
                    await agree_btn.click()
                    await page.wait_for_load_state("domcontentloaded", timeout=60000)
            except Exception:
                break

        log.info(f"→ Đăng nhập hoàn tất. URL hiện tại: {page.url}")
        return "ALREADY_LOGGED_IN"

    # ─── ĐĂNG KÝ MỚI (has_bnid = False) ───
    # ─── ĐĂNG KÝ MỚI (has_bnid = False) ───
    if "-" in birthday:
        parts = birthday.split("-")
        birth_year = parts[0]
        birth_month = parts[1]
        birth_day = parts[2]
    else:
        birth_year = birthday[:4]
        birth_month = birthday[4:6]
        birth_day = birthday[6:]
    birthday_str = birthday
    
    log.info(f"1. Điền Email ({email}) & Mật khẩu...")
    await page.wait_for_selector("input#mail, input[name='mail']", timeout=20000)
    await human_delay(page, 800, 1500)

    email_field = page.locator("input#mail, input[name='mail']")
    await email_field.fill(email)
    await human_delay(page, 500, 1000)
    await email_field.blur()

    await human_delay(page, 800, 1500)
    pass_field = page.locator("input#pass, input[name='pass']")
    await pass_field.fill(password)
    await human_delay(page, 500, 1000)
    await pass_field.blur()

    # Tick các checkbox đồng ý điều khoản ban đầu
    await human_delay(page, 600, 1200)
    checkboxes = await page.query_selector_all("input[type='checkbox']")
    for cb in checkboxes:
        await cb.evaluate("el => { if (!el.checked) el.click(); }")
        await page.wait_for_timeout(random.randint(200, 500))
    log.info(f"   Đã tick {len(checkboxes)} checkbox điều khoản ban đầu.")

    # Submit form đăng ký Email/Password (Nút id='btn-idpw-next')
    log.info("2. Submit form đăng ký Email/Password...")
    await human_delay(page, 1000, 2000)
    submit_btn = await page.wait_for_selector("button#btn-idpw-next", timeout=60000)
    await submit_btn.click()
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass
    # Chờ trang phản hồi chuyển sang DOB page hoặc báo lỗi/redirect sang passkey
    is_already_in_use = False
    log.info("   Đang chờ phản hồi từ hệ thống để xác định trạng thái tài khoản...")
    for _ in range(30):  # Đợi tối đa 15 giây
        await page.wait_for_timeout(500)
        current_url = page.url
        try:
            page_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        except Exception:
            page_text = ""
            # Bỏ qua nếu trang đang chuyển hướng
            pass

        # 1. Check nếu có text báo lỗi email đã được sử dụng
        email_in_use_markers = [
            "already in use",
            "already registered",
            "既に使用されています",
            "登録済みのメールアドレス",
            "使用されています",
            "登録済み"
        ]
        if any(marker in page_text for marker in email_in_use_markers):
            log.warning(f"⚠️ Phát hiện lỗi trùng email hiển thị trên trang!")
            is_already_in_use = True
            break

        # 2. Check nếu bị chuyển sang màn hình Passkey (passkeyInfo.html)
        if "passkeyInfo.html" in current_url or "passkey" in current_url.lower():
            log.warning(f"⚠️ Phát hiện đã chuyển hướng sang passkeyInfo.html!")
            is_already_in_use = True
            break

        # 3. Check nếu đã vào trang nhập Ngày sinh (input#id_year hiển thị)
        dob_el = await page.query_selector("input#id_year")
        if dob_el and await dob_el.is_visible():
            log.info("   ✅ Giao diện nhập Quốc gia / Ngày sinh đã hiển thị.")
            break

    if is_already_in_use:
        raise RuntimeError("EMAIL_ALREADY_IN_USE")

    # Chờ input#id_year được gắn vào DOM
    await page.wait_for_selector(
        "input#id_year",
        state="attached",
        timeout=60000
    )

    await human_delay(page, 1000, 2000)

    # Chọn Quốc gia = Japan
    try:
        selects = await page.query_selector_all("select")
        for sel in selects:
            name = await sel.get_attribute("name") or ""
            sid = await sel.get_attribute("id") or ""
            options = await sel.query_selector_all("option")
            for opt in options:
                val = await opt.get_attribute("value") or ""
                if val in ["JP", "japan", "Japan", "JPN", "392"]:
                    # Dùng JS để chọn để tránh Playwright bị block do element bị che/ẩn
                    await sel.evaluate(f"el => {{ el.value = '{val}'; el.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
                    log.info(f"   Đã chọn Quốc gia (JS): {val} (select[name='{name}'][id='{sid}'])")
                    await page.wait_for_timeout(500)
                    break
    except Exception as e:
        log.warning(f"   Lỗi chọn quốc gia: {e}")

    # Điền Ngày sinh (Dạng input text type=number)
    await human_delay(page, 800, 1500)
    try:
        month_loc = page.locator("input#id_month")
        day_loc = page.locator("input#id_day")
        year_loc = page.locator("input#id_year")

        if await month_loc.count() > 0 and await day_loc.count() > 0 and await year_loc.count() > 0:
            # Dùng JS evaluate để điền DOB để tránh bị block do khuất/ẩn
            await month_loc.evaluate(f"el => {{ el.value = '{str(int(birth_month))}'; el.dispatchEvent(new Event('input', {{bubbles: true}})); el.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
            await page.wait_for_timeout(300)
            await day_loc.evaluate(f"el => {{ el.value = '{str(int(birth_day))}'; el.dispatchEvent(new Event('input', {{bubbles: true}})); el.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
            await page.wait_for_timeout(300)
            await year_loc.evaluate(f"el => {{ el.value = '{birth_year}'; el.dispatchEvent(new Event('input', {{bubbles: true}})); el.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
            log.info(f"   Đã điền ngày sinh (JS) (M/D/Y): {birth_month}/{birth_day}/{birth_year}")
            await page.wait_for_timeout(1000)
        else:
            # Fallback select options
            y_sel = await page.query_selector("select[name='birthYear'], select[name='year']")
            if y_sel:
                await y_sel.evaluate(f"el => {{ el.value = '{birth_year}'; el.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
            m_sel = await page.query_selector("select[name='birthMonth'], select[name='month']")
            if m_sel:
                await m_sel.evaluate(f"el => {{ el.value = '{str(int(birth_month))}'; el.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
            d_sel = await page.query_selector("select[name='birthDay'], select[name='day']")
            if d_sel:
                await d_sel.evaluate(f"el => {{ el.value = '{str(int(birth_day))}'; el.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
            log.info(f"   Đã chọn ngày sinh từ select box (JS): {birthday_str}")
    except Exception as e:
        log.warning(f"   Lỗi điền ngày sinh: {e}")

    # Tick tất cả checkbox bổ sung đồng ý điều khoản & global consent
    await human_delay(page, 600, 1200)
    extra_cbs = await page.query_selector_all("input[type='checkbox']")
    for cb in extra_cbs:
        await cb.evaluate("el => { if (!el.checked) el.click(); }")
        await page.wait_for_timeout(random.randint(200, 500))
    log.info(f"   Đã tick {len(extra_cbs)} checkbox bổ sung.")

    # Submit thông tin cơ bản (Nút id='btn-agree-b')
    log.info("4. Submit thông tin cơ bản (Quốc gia/Ngày sinh)...")
    await human_delay(page, 1000, 2000)

    try:
        await page.wait_for_selector(".c-loader-wrap, [class*='loader']", state="hidden", timeout=5000)
    except Exception:
        pass

    final_btn = await page.wait_for_selector("button#btn-agree-b", timeout=60000)
    await final_btn.click()
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass
    log.info(f"   → URL hiện tại: {page.url}")

    # ─── BƯỚC 5. Đọc OTP từ Email (Chuyển sang dùng router Web/IMAP bất đồng bộ)
    # Đợi Bandai Namco xử lý và load xong trang nhập OTP trước khi lật sang tab Mail
    log.info("   Đang chờ Bandai Namco xử lý form và hiện ô nhập OTP...")
    try:
        await page.wait_for_selector("input[name='authenticationCode'], input[name='code'], input[name='otp'], input[type='text']", timeout=60000)
    except:
        pass
    await page.wait_for_timeout(3000) # Đợi thêm 3s cho chắc chắn Bandai đã gửi mail đi

    log.info("5. Đang poll OTP email (Web/IMAP)...")
    email_otp = await get_bandai_namco_otp(
        context=page.context,
        target_email=email,
        target_password=email_password,
        since_ts=since_ts,
        timeout=config.EMAIL_OTP_TIMEOUT,
        mail_page=mail_page,
        refresh_token=refresh_token,
        client_id=client_id
    )

    if not email_otp:
        if not config.STOP_FLAG:
            sc_path = str(config.DATA_DIR / f"err_email_otp_{int(time.time())}.png")
            try:
                import asyncio
                await asyncio.wait_for(page.screenshot(path=sc_path), timeout=5.0)
            except Exception:
                pass
        raise TimeoutError(f"Không nhận được OTP email sau {config.EMAIL_OTP_TIMEOUT}s!")

    # Đưa focus quay lại tab Bandai Namco để điền OTP cho người dùng thấy
    await page.bring_to_front()
    await page.wait_for_timeout(1000)

    log.info(f"✅ → OTP email: {email_otp}. Điền vào form...")
    await human_delay(page, 800, 1500)

    # Dùng locator thay vì wait_for_selector để tránh lỗi ElementHandle không có .blur()
    otp_selector = "input[name='authenticationCode'], input[name='code'], input[name='otp'], input[type='text']"
    await page.wait_for_selector(otp_selector, timeout=60000)
    otp_loc = page.locator(otp_selector).first
    await otp_loc.fill(str(email_otp))
    await human_delay(page, 500, 1000)
    await otp_loc.blur()  # Locator.blur() hoạt động đúng, kích hoạt cập nhật trạng thái nút

    # Submit OTP
    log.info("   Đã blur OTP field. Đang click nút submit OTP...")
    await human_delay(page, 800, 1500)
    otp_submit_sel = "button[type='submit'], button.c-button--primary, button:has-text('Authenticate'), button:has-text('次へ'), button:has-text('送信'), button:has-text('確認')"
    otp_submit = await page.wait_for_selector(otp_submit_sel, timeout=60000)
    await otp_submit.click()
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=25000)
    except Exception:
        pass
    log.info(f"   → URL sau OTP submit: {page.url}")

    # ─── BƯỚC 3.4: Xử lý các màn hình trung gian (Data collection) ───
    log.info("6. Xử lý các màn hình trung gian sau OTP...")
    
    for step_idx in range(4):  # Quét tối đa 4 màn hình trung gian
        await human_delay(page, 1500, 3000)
        
        try:
            current_url = page.url
            log.info(f"   - [Màn hình {step_idx + 1}] URL: {current_url}")
                    
            # Nếu đã bị redirect về Namco Parks, thì ngắt vòng lặp
            if "parks2.bandainamco-am.co.jp" in current_url:
                log.info("   Đã chuyển hướng về Namco Parks.")
                break

            # Tìm nút bấm để đi tiếp (Agree, Next, Continue, OK)
            next_btn = await page.query_selector(
                "button:has-text('同意する'), button:has-text('次へ'), button:has-text('OK'), button:has-text('Continue'), button:has-text('Agree'), button:has-text('Accept'), button.c-button--primary"
            )
            if next_btn and await next_btn.is_visible():
                log.info("   Tìm thấy nút đi tiếp. Đang click để qua màn hình này...")
                await next_btn.click()
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=60000)
                except Exception:
                    pass
            else:
                log.info("   Không tìm thấy nút đi tiếp hoặc đã tự động chuyển hướng.")
                if step_idx >= 1:
                    break
                    
        except Exception as e:
            log.debug(f"   Lỗi khi xử lý màn hình trung gian: {e}")
            break

    log.info(f"   → Hoàn thành Giai đoạn đăng ký BNID. URL: {page.url}")
    return "TRUE"
