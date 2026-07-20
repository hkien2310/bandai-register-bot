import time
import random
import re
import asyncio
from playwright.async_api import Page
import src.config as config
from src.core.email_reader import get_bandai_namco_otp
from src.utils.logger import get_logger

log = get_logger("step3_bnid_register")


async def human_delay(page: Page, min_ms: int = 800, max_ms: int = 2000):
    """Delay ngẫu nhiên giả lập hành động người dùng."""
    delay = random.randint(min_ms, max_ms)
    await page.wait_for_timeout(delay)

async def handle_email_otp(page: Page, email: str, email_password: str, since_ts: float, mail_page, refresh_token: str = None, client_id: str = None, otp_email: str = "", otp_pass: str = "", provider: str = ""):
    log.info("   [Màn hình OTP] Bắt đầu màn hình OTP...")
    log.info("   [Màn hình OTP] Đang chờ Bandai Namco xử lý form và hiện ô nhập OTP...")
    try:
        await page.wait_for_selector("input[name='authenticationCode'], input[name='code'], input[name='otp'], input[type='text']", timeout=60000)
    except:
        pass
    await page.wait_for_timeout(3000) # Đợi thêm 3s cho chắc chắn Bandai đã gửi mail đi

    log.info("   [Màn hình OTP] Đang thực hiện lấy OTP...")
    email_otp = await get_bandai_namco_otp(
        context=page.context,
        target_email=email,
        target_password=email_password,
        since_ts=since_ts,
        timeout=config.EMAIL_OTP_TIMEOUT,
        mail_page=mail_page,
        refresh_token=refresh_token,
        client_id=client_id,
        otp_email=otp_email,
        otp_pass=otp_pass,
        provider=provider
    )

    if not email_otp:
        if not config.STOP_FLAG:
            import time
            sc_path = str(config.DATA_DIR / f"err_email_otp_{int(time.time())}.png")
            try:
                import asyncio
                await page.screenshot(path=sc_path, timeout=5000)
            except Exception:
                pass
        log.error("   [Màn hình OTP] Thất bại: Không lấy được OTP từ email.")
        raise TimeoutError(f"Không nhận được OTP email sau {config.EMAIL_OTP_TIMEOUT}s!")

    # Đưa focus quay lại tab Bandai Namco để điền OTP cho người dùng thấy
    await page.bring_to_front()
    await page.wait_for_timeout(1000)

    log.info(f"   [Màn hình OTP] Đã nhận OTP: {email_otp}. Đang điền vào form...")
    await human_delay(page, 800, 1500)

    # Dùng locator thay vì wait_for_selector để tránh lỗi ElementHandle không có .blur()
    otp_selector = "input[name='authenticationCode'], input[name='code'], input[name='otp'], input[type='text']"
    await page.wait_for_selector(otp_selector, timeout=60000)
    otp_loc = page.locator(otp_selector).first
    await otp_loc.fill(str(email_otp), timeout=15000)
    await human_delay(page, 500, 1000)
    await otp_loc.blur()  # Locator.blur() hoạt động đúng, kích hoạt cập nhật trạng thái nút

    # Submit OTP
    log.info("   [Màn hình OTP] Đang click nút submit OTP...")
    await human_delay(page, 800, 1500)
    otp_submit_sel = "button[type='submit'], button.c-button--primary, button:has-text('Authenticate'), button:has-text('次へ'), button:has-text('送信'), button:has-text('確認')"
    otp_submit = await page.wait_for_selector(otp_submit_sel, timeout=60000)
    await otp_submit.click()
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=25000)
    except Exception:
        pass
    log.info(f"   [Màn hình OTP] Đã hoàn thành màn hình OTP (điều kiện phải qua màn sau). URL sau submit: {page.url}")


async def run_step3(page: Page, email: str, password: str, birthday: str, has_bnid: bool = False, email_password: str = "", refresh_token: str = None, client_id: str = None, otp_email: str = "", otp_pass: str = "", provider: str = "") -> str:
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

    # Kiểm tra xem Bandai Namco có trả về trang lỗi System Error (IP Ban / Quá tải) không
    try:
        page_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        if "A system error has occurred" in page_text or "エラー" in page_text or "アクセス集中" in page_text:
            log.error("❌ Bandai Namco trả về trang 'System Error' (Có thể do quá tải hoặc Ban IP).")
            raise Exception("SITE_OVERLOADED: A system error has occurred.")
    except Exception as e:
        if "SITE_OVERLOADED" in str(e): raise
        pass
    
    if has_bnid:
        log.info(f"--- THỰC HIỆN ĐĂNG NHẬP BANDAI NAMCO ID ({email}) ---")
        await page.wait_for_selector("input#mail, input[name='mail']", timeout=20000)
        await human_delay(page, 600, 1200)

        # Ẩn cookie banner nếu có để tránh che khuất input
        try:
            cookie_btn = await page.query_selector("button#onetrust-accept-btn-handler")
            if cookie_btn and await cookie_btn.is_visible():
                await cookie_btn.click()
                await page.wait_for_timeout(500)
        except Exception:
            pass

        email_field = page.locator("input#mail, input[name='mail']")
        await email_field.fill(email, timeout=15000)
        await human_delay(page, 400, 800)
        await email_field.blur()

        pass_field = page.locator("input#pass, input[name='pass']")
        await human_delay(page, 600, 1200)
        await pass_field.fill(password, timeout=15000)
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

        # === KIỂM TRA LỖI SAU KHI LOGIN ===
        await page.wait_for_timeout(2000)
        try:
            page_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            # Lỗi vùng/quốc gia bị chặn
            if "country or region" in page_text.lower() or "isn't available" in page_text.lower():
                log.error(f"❌ Account bị chặn vùng: {page_text[:150]}")
                raise RuntimeError("REGION_BLOCKED: Service not available in this country/region")
            # Lỗi sai mật khẩu hoặc giới hạn đăng nhập do sai nhiều lần
            if "incorrect" in page_text.lower() or "パスワードが正しくありません" in page_text or "login restriction" in page_text.lower() or "wrong password" in page_text.lower():
                log.error("❌ Sai email hoặc mật khẩu BNID, hoặc account bị giới hạn đăng nhập!")
                raise RuntimeError("WRONG_PASSWORD: Email hoặc mật khẩu BNID không đúng / Bị giới hạn đăng nhập")
            # Lỗi trang Error chung
            if page_text.strip().startswith("Error") and "error" in page_text.lower():
                log.error(f"❌ Trang lỗi Bandai: {page_text[:200]}")
                raise RuntimeError(f"BNID_LOGIN_ERROR: {page_text[:150]}")
        except RuntimeError:
            raise
        except Exception:
            pass

        # === KIỂM TRA AUTH CODE (OTP) ===
        if "authCode.html" in page.url or await page.query_selector("input[name='authenticationCode']"):
            log.info("⚠️ Bandai Namco yêu cầu xác thực 2 bước (OTP) khi đăng nhập thiết bị lạ!")
            await handle_email_otp(page, email, email_password, since_ts, mail_page, refresh_token, client_id, otp_email, otp_pass, provider)

        # Xử lý các màn hình đồng ý điều khoản bổ sung hoặc điền thông tin nếu có khi login
        log.info("Kiểm tra màn hình chấp nhận điều khoản bổ sung / nhập thông tin khi đăng nhập...")
        for _ in range(5):
            await page.wait_for_timeout(1000)
            try:
                current_url = page.url
                
                # Check nếu đã vào trang nhập Ngày sinh (input#id_year hiển thị)
                dob_el = await page.query_selector("input#id_year")
                if dob_el and await dob_el.is_visible():
                    log.info("   ✅ Giao diện nhập Quốc gia / Ngày sinh chèn ngang đã hiển thị. Tiến hành điền...")
                    
                    if "-" in birthday:
                        parts = birthday.split("-")
                        birth_year, birth_month, birth_day = parts[0], parts[1], parts[2]
                    else:
                        birth_year, birth_month, birth_day = birthday[:4], birthday[4:6], birthday[6:]
                    
                    # Chọn Quốc gia = Japan
                    try:
                        selects = await page.query_selector_all("select")
                        for sel in selects:
                            val = await sel.get_attribute("value") or ""
                            options = await sel.query_selector_all("option")
                            for opt in options:
                                opt_val = await opt.get_attribute("value") or ""
                                if opt_val in ["JP", "japan", "Japan", "JPN", "392"]:
                                    await sel.evaluate(f"el => {{ el.value = '{opt_val}'; el.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
                                    await page.wait_for_timeout(500)
                                    break
                    except Exception:
                        pass

                    # Điền Ngày sinh
                    try:
                        month_loc = page.locator("input#id_month")
                        day_loc = page.locator("input#id_day")
                        year_loc = page.locator("input#id_year")
                        if await month_loc.count() > 0 and await day_loc.count() > 0 and await year_loc.count() > 0:
                            await month_loc.evaluate(f"el => {{ el.value = '{str(int(birth_month))}'; el.dispatchEvent(new Event('input', {{bubbles: true}})); el.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
                            await page.wait_for_timeout(300)
                            await day_loc.evaluate(f"el => {{ el.value = '{str(int(birth_day))}'; el.dispatchEvent(new Event('input', {{bubbles: true}})); el.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
                            await page.wait_for_timeout(300)
                            await year_loc.evaluate(f"el => {{ el.value = '{birth_year}'; el.dispatchEvent(new Event('input', {{bubbles: true}})); el.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
                            await page.wait_for_timeout(1000)
                    except Exception:
                        pass

                    # Tick checkbox
                    cbs = await page.query_selector_all("input[type='checkbox']")
                    for cb in cbs:
                        await cb.evaluate("""el => { 
                            if (!el.checked) {
                                if (el.labels && el.labels.length > 0) {
                                    el.labels[0].click();
                                } else if (el.parentElement && el.parentElement.tagName === 'LABEL') {
                                    el.parentElement.click();
                                } else {
                                    el.click();
                                }
                            }
                        }""")
                        
                    agree_btn = await page.query_selector("button#btn-agree-b, button#btn-accept-all")
                    if agree_btn:
                        log.info("   Đã điền xong DOB, click nút Continue...")
                        await agree_btn.click()
                        await page.wait_for_load_state("domcontentloaded", timeout=60000)
                        await page.wait_for_timeout(2000)
                    break
                    
                # Chỉ là terms review bình thường
                elif "disp=terms" in current_url:
                    try:
                        await page.wait_for_selector("input[type='checkbox']", timeout=10000)
                    except Exception:
                        pass
                    
                    cbs = await page.query_selector_all("input[type='checkbox']")
                    for cb in cbs:
                        try:
                            await cb.check(force=True)
                        except Exception:
                            await cb.evaluate("el => { if (!el.checked) el.click(); }")
                        await page.wait_for_timeout(300)

                    agree_btn = await page.query_selector("button#btn-agree-b, button#btn-accept-all")
                    if agree_btn:
                        log.info("Phát hiện và click nút đồng ý điều khoản bổ sung...")
                        await agree_btn.click()
                        await page.wait_for_load_state("domcontentloaded", timeout=60000)
                        await page.wait_for_timeout(2000)
                        break
            except Exception:
                pass

        if "login.html" in page.url:
            raise RuntimeError("BNID_LOGIN_ERROR: Đăng nhập không thành công, vẫn kẹt ở trang login (sai mật khẩu hoặc captcha).")
            
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

    # Ẩn cookie banner nếu có để tránh che khuất input
    try:
        cookie_btn = await page.query_selector("button#onetrust-accept-btn-handler")
        if cookie_btn and await cookie_btn.is_visible():
            await cookie_btn.click()
            await page.wait_for_timeout(500)
    except Exception:
        pass

    email_field = page.locator("input#mail, input[name='mail']")
    await email_field.fill(email, timeout=15000)
    await human_delay(page, 500, 1000)
    await email_field.blur()

    await human_delay(page, 800, 1500)
    pass_field = page.locator("input#pass, input[name='pass']")
    await pass_field.fill(password, timeout=15000)
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

        # 0. Check lỗi region/country bị chặn (có thể xuất hiện ở cả đăng ký lẫn đăng nhập)
        if "country or region" in page_text.lower() or "isn't available" in page_text.lower():
            log.error(f"❌ Account bị chặn vùng: {page_text[:150]}")
            raise RuntimeError("REGION_BLOCKED: Service not available in this country/region")

        # 1. Check nếu có text báo lỗi email đã được sử dụng
        email_in_use_markers = [
            "already in use",
            "already registered",
            "既に使用されています",
            "登録済みのメールアドレス",
            "使用されています",
            "登録済み"
        ]
        
        # Check explicit error areas
        try:
            err_text = await page.evaluate('''() => {
                let err1 = document.querySelector('#error-input-area:not(.u-hide)');
                let err2 = document.querySelector('#error-terms:not(.u-hide)');
                return (err1 ? err1.innerText : '') + ' ' + (err2 ? err2.innerText : '');
            }''')
            if err_text and err_text.strip():
                log.error(f"⚠️ Bandai trả về lỗi trên form: {err_text.strip()}")
                if any(marker in err_text for marker in email_in_use_markers):
                    is_already_in_use = True
                    break
                else:
                    raise RuntimeError(f"FORM_ERROR: {err_text.strip()}")
        except Exception as e:
            if isinstance(e, RuntimeError) and "FORM_ERROR" in str(e):
                raise e
            pass
            
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
            
        # 4. Check nếu bị chèn ngang trang Terms Review
        # Nếu url chứa login.html và disp=terms, đây là trang Review điều khoản chứ không phải trang DOB
        if "disp=terms" in current_url and "login.html" in current_url:
            log.info("   👉 Phát hiện trang Terms Review chèn ngang. Tick checkbox + click Continue...")
            
            try:
                await page.evaluate("if (document.body) { window.scrollTo(0, document.body.scrollHeight); }")
                await page.wait_for_timeout(500)
            except Exception:
                pass
                
            try:
                await page.wait_for_selector("input[type='checkbox']", timeout=10000)
            except Exception:
                pass
                
            cbs = await page.query_selector_all("input[type='checkbox']")
            for cb in cbs:
                try:
                    await cb.check(force=True)
                except Exception:
                    await cb.evaluate("el => { if (!el.checked) el.click(); }")
                await page.wait_for_timeout(300)

            try:
                next_btns = await page.query_selector_all(
                    "button#btn-agree-b, button#btn-accept-all, button:has-text('同意する'), button:has-text('次へ'), button:has-text('OK'), button:has-text('Continue'), button.c-button--primary:not(:has-text('Disagree'))"
                )
                
                next_btn = None
                for btn in next_btns:
                    if await btn.is_visible() and not await btn.is_disabled():
                        next_btn = btn
                        break
                        
                if next_btn:
                    log.info("   Tìm thấy nút đi tiếp. Đang click để qua màn hình này...")
                    await next_btn.click(timeout=5000)
                    await page.wait_for_timeout(3000)
                else:
                    log.warning("   Không tìm thấy nút Continue nào hợp lệ hoặc click thất bại.")
            except Exception as e:
                log.warning(f"   Lỗi khi click nút Continue: {e}")
            continue

    if is_already_in_use:
        raise RuntimeError("EMAIL_ALREADY_IN_USE")

    # Chờ input#id_year được gắn vào DOM
    try:
        await page.wait_for_selector(
            "input#id_year",
            state="attached",
            timeout=60000
        )
    except Exception as e:
        log.error(f"Lỗi Timeout khi đợi input#id_year tại URL: {page.url}")
        try:
            from src import config as _cfg
            screenshot_path = str(_cfg.DATA_DIR / f"timeout_step3_{email}.png")
            await page.screenshot(path=screenshot_path, full_page=True, timeout=5000)
            log.info(f"Đã lưu ảnh màn hình lỗi tại: {screenshot_path}")
        except Exception as img_e:
            log.debug(f"Không thể chụp ảnh màn hình: {img_e}")
        raise e

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
    
    try:
        await page.wait_for_selector("input[type='checkbox']", timeout=10000)
    except Exception:
        pass
        
    extra_cbs = await page.query_selector_all("input[type='checkbox']")
    for cb in extra_cbs:
        try:
            await cb.check(force=True)
        except Exception:
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

    # ─── BƯỚC 5. Đọc OTP từ Email (Dùng helper)
    log.info("5. Đọc OTP từ Email...")
    await handle_email_otp(page, email, email_password, since_ts, mail_page, refresh_token, client_id, otp_email, otp_pass, provider)

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
                "button:has-text('同意する'), button:has-text('次へ'), button:has-text('OK'), button:has-text('Continue'), button:has-text('Agree'), button:has-text('Accept'), button.c-button--primary, button:has-text('Proceed to Service'), a:has-text('Proceed to Service'), a.c-button--primary"
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
