import re
import asyncio
from urllib.parse import urlparse
import src.config as config
import src.core.sms_service as sms_service
from playwright.async_api import Page
from src.utils.logger import get_logger

log = get_logger("step4_parks_profile")

def format_jp_phone(phone_raw: str) -> str:
    phone = phone_raw.strip().replace("+", "").replace("-", "").replace(" ", "")
    if phone.startswith("81"):
        phone = "0" + phone[2:]
    if not phone.startswith("0") and len(phone) in [9, 10]:
        phone = "0" + phone
    return phone

async def run_step4(page: Page, email: str, password: str, nickname: str, birthday_str: str, prefecture: str) -> tuple[str, str]:
    """
    Step 4: Điền thông tin profile Namco Parks & Thuê số điện thoại
    """
    birth_year, birth_month, birth_day = birthday_str.split("-")

    log.info("1. Xử lý trang Terms / Privacy consent và chờ về Namco Parks...")

    def is_on_parks_form(url: str) -> bool:
        """Kiểm tra chính xác host là parks2.bandainamco-am.co.jp và path chứa member_regist_new hoặc member_regist."""
        try:
            parsed = urlparse(url)
            return (parsed.netloc == "parks2.bandainamco-am.co.jp"
                    and ("member_regist_new.html" in parsed.path or "member_regist.html" in parsed.path))
        except Exception:
            return False


    async def handle_cookie_banner():
        """Click Accept All Cookies nếu có cookie banner."""
        for sel in [
            "button:has-text('Accept All Cookies')",
            "button:has-text('Accept all')",
            "button:has-text('Accept All')",
        ]:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    log.info(f"   [Cookie Banner] Click: {sel}")
                    await btn.click()
                    await page.wait_for_timeout(1000)
                    return
            except Exception:
                continue

    # Chờ tối đa 90s — đi qua các trang trung gian
    for attempt in range(18):
        current_url = page.url
        log.info(f"   [Attempt {attempt+1}] URL: {current_url}")

        if is_on_parks_form(current_url):
            log.info("   ✅ Đã về trang đăng ký thành viên Namco Parks!")
            break

        # Nếu chuyển hướng thẳng sang trang sms_authentication (xác thực sđt) hoặc trang mypage/member
        # mà không qua form đăng ký (member_regist_new), nghĩa là tài khoản đã liên kết Namco Parks từ trước
        if "sms_authentication.html" in current_url or "mypage" in current_url.lower():
            log.warning("   ⚠️ Phát hiện URL đã liên kết Namco Parks từ trước! Bỏ qua đăng ký.")
            return "ALREADY_REGISTERED", "ALREADY_REGISTERED"

        # Trang trung gian (signupEnd, authCode, terms, login, privacy...)
        # Xử lý trên bất kỳ trang nào không phải là form chính của Parks
        if not is_on_parks_form(current_url):
            log.info("   Phát hiện trang trung gian. Xử lý...")

            # 1. Xử lý cookie banner trước
            await handle_cookie_banner()
            await page.wait_for_timeout(500)

            # 2. XỬ LÝ RIÊNG CHO MÀN HÌNH PASSKEY (BẮT BUỘC CLICK LATER/SKIP)
            is_passkey_page = "passkeyInfo.html" in current_url or "passkey" in current_url.lower()
            if is_passkey_page:
                log.info("   👉 Đang ở màn hình Passkey. Bắt buộc tìm và click Later/Skip...")
                clicked_later = False
                # Thử tìm và click Later/Skip trong tối đa 5 giây
                for _ in range(10):
                    for later_sel in [
                        "button#btn-next", "#btn-next", "button.c-button--secondary",
                        "button:has-text('Later')", "button:has-text('later')", "button:has-text('LATER')",
                        "button:has-text('後で')", "button:has-text('スキップ')", "button:has-text('Skip')", "button:has-text('skip')",
                        "button:has-text('Not now')", "button:has-text('not now')",
                        "a:has-text('Later')", "a:has-text('later')", "a:has-text('後で')",
                        "a:has-text('Skip')", "a:has-text('skip')", "a:has-text('Not now')", "a:has-text('not now')",
                        "span:has-text('Later')", "span:has-text('later')", "span:has-text('後で')",
                        "span:has-text('Skip')", "span:has-text('skip')",
                    ]:
                        try:
                            # Try to wait for it specifically if it's the ID
                            if later_sel == "button#btn-next" or later_sel == "#btn-next":
                                btn = await page.wait_for_selector(later_sel, timeout=1000, state="visible")
                            else:
                                btn = await page.query_selector(later_sel)
                            if btn and await btn.is_visible():
                                log.info(f"   [Passkey] Click nút bỏ qua: {later_sel}")
                                await btn.click()
                                await page.wait_for_timeout(2500)
                                clicked_later = True
                                break
                        except Exception:
                            continue
                    if clicked_later:
                        break
                    await page.wait_for_timeout(500)
                
                if clicked_later:
                    continue
                else:
                    html_content = await page.content()
                    with open(f"data/passkey_dump_{email}.html", "w", encoding="utf-8") as f_html:
                        f_html.write(html_content)
                    log.error(f"   [Passkey] Dumped HTML to data/passkey_dump_{email}.html")
                    raise RuntimeError("Bắt buộc phải click Later trên màn hình Passkey nhưng không tìm thấy nút!")

            # 3. KIỂM TRA PHÁT HIỆN NÚT LATER/SKIP TRÊN CÁC TRANG TRUNG GIAN KHÁC (nếu có) -> CLICK BỎ QUA
            clicked_later = False
            for later_sel in [
                "button:has-text('Later')",
                "button:has-text('later')",
                "button:has-text('LATER')",
                "button:has-text('後で')",
                "button:has-text('スキップ')",
                "button:has-text('Skip')",
                "button:has-text('skip')",
                "button:has-text('Not now')",
                "button:has-text('not now')",
                "a:has-text('Later')",
                "a:has-text('later')",
                "a:has-text('後で')",
                "a:has-text('Skip')",
                "a:has-text('skip')",
                "a:has-text('Not now')",
                "a:has-text('not now')",
                "span:has-text('Later')",
                "span:has-text('later')",
                "span:has-text('後で')",
                "span:has-text('Skip')",
                "span:has-text('skip')",
            ]:
                try:
                    btn = await page.query_selector(later_sel)
                    if btn and await btn.is_visible():
                        log.info(f"   👉 Phát hiện và click nút bỏ qua: {later_sel}")
                        await btn.click()
                        await page.wait_for_timeout(2500)
                        clicked_later = True
                        break
                except Exception:
                    continue
            if clicked_later:
                continue

            # *** Hủy dialog Bluetooth/Save another way nếu có ***
            if "passkeyInfo.html" in current_url or "passkey" in current_url.lower():
                for cancel_sel in ["button:has-text('Cancel')", "button:has-text('Save another way')"]:
                    try:
                        btn = await page.query_selector(cancel_sel)
                        if btn and await btn.is_visible():
                            log.info(f"   Đóng Bluetooth dialog: {cancel_sel}")
                            await btn.click()
                            await page.wait_for_timeout(1000)
                            break
                    except Exception:
                        continue


            # 2. Nếu là trang "Please review our terms" (login.html?disp=terms)
            if "disp=terms" in current_url or "login.html" in current_url:
                log.info("   Phát hiện trang Terms Review. Tick checkbox + click Agree...")
                # Tick checkbox 'I agree to the above statements.'
                try:
                    checkbox = await page.query_selector("input[type='checkbox']")
                    if checkbox:
                        await checkbox.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change', {bubbles:true})); el.dispatchEvent(new Event('click', {bubbles:true})); }")
                        log.info("   Đã tick checkbox 'I agree'.")
                        await page.wait_for_timeout(800)
                except Exception as e:
                    log.warning(f"   Không thể tick checkbox: {e}")

                # Cuộn xuống để thấy nút Agree
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(500)
                except Exception as e:
                    log.warning(f"   Lỗi khi cuộn trang: {e}")

                # Click nút Agree (không phải Disagree)
                try:
                    agreed = False
                    for agree_sel in [
                        "button:text-is('Agree')",
                        "button:text-is('同意する')",
                        "button:text-is('同意')",
                        "button.c-button--primary:not(:has-text('Disagree')):not(:has-text('不同意'))",
                    ]:
                        try:
                            btn = await page.query_selector(agree_sel)
                            if btn and await btn.is_visible():
                                txt = (await btn.inner_text()).strip()
                                log.info(f"   Click Agree: '{txt}'")
                                await btn.click()
                                agreed = True
                                await page.wait_for_timeout(3000)
                                break
                        except Exception:
                            continue

                    if not agreed:
                        # Dump tất cả button dể debug
                        btns = await page.query_selector_all("button")
                        log.warning(f"   Dump {len(btns)} buttons:")
                        for b in btns:
                            txt = (await b.inner_text()).strip()[:60]
                            vis = await b.is_visible()
                            log.warning(f"     '{txt}' visible={vis}")
                except Exception as e:
                    log.warning(f"   Lỗi khi click nút Agree hoặc dump button: {e}")
                
                continue  # Loop lại sau khi xử lý terms

            # 3. Xử lý các trang trung gian khác (signupEnd, privacy toggles...)
            try:
                toggles = await page.query_selector_all("input[type='checkbox'], input[type='radio']")
                for t in toggles:
                    await t.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change', {bubbles:true})); }")
                if toggles:
                    log.info(f"   Đã tick {len(toggles)} toggle.")
                    await page.wait_for_timeout(600)
            except Exception:
                pass

            # Click nút đồng ý theo thứ tự ưu tiên
            accepted = False
            for btn_sel in [
                "button:has-text('同意する')",
                "button:has-text('利用規約に同意する')",
                "button:has-text('Save settings')",
                "button:has-text('Accept all')",
                "button:has-text('同意')",
                "button:has-text('OK')",
                "button:has-text('Continue')",
                "button:has-text('Complete account profile')",
                "button:has-text('次へ')",
                "button.c-button--primary",
                "button[type='submit']",
            ]:
                try:
                    btn = await page.query_selector(btn_sel)
                    if btn and await btn.is_visible():
                        log.info(f"   Click: {btn_sel}")
                        await btn.click()
                        accepted = True
                        await page.wait_for_timeout(2500)
                        break
                except Exception:
                    continue

            if not accepted:
                try:
                    btns = await page.query_selector_all("button")
                    log.warning(f"   Dump {len(btns)} button trên trang:")
                    for b in btns:
                        txt = (await b.inner_text()).strip()[:60]
                        vis = await b.is_visible()
                        log.warning(f"     '{txt}' visible={vis}")
                except Exception:
                    pass
                log.warning("   Không tìm thấy nút nào cần click. Đợi trang tự động chuyển hướng...")
                await page.wait_for_timeout(3000)

    # Fallback nếu vẫn chưa đến đúng trang
    if not is_on_parks_form(page.url):
        log.warning(f"   Fallback: Navigate thẳng (URL hiện tại: {page.url})")
        await page.goto(
            "https://parks2.bandainamco-am.co.jp/member_regist_new.html",
            wait_until="commit",
            timeout=90000,
        )

    log.info(f"   ✅ Đã vào form đăng ký Parks. URL: {page.url}")

    # Dismiss cookie banner trên trang Parks nếu có
    for ck_sel in ["button:has-text('Accept All Cookies')", "button:has-text('Accept all')", "button:has-text('同意')"]:
        try:
            btn = await page.query_selector(ck_sel)
            if btn and await btn.is_visible():
                log.info(f"   [Parks Cookie] Click: {ck_sel}")
                await btn.click()
                await page.wait_for_timeout(1000)
                break
        except Exception:
            continue

    # Đợi trang Parks load ổn định
    await page.wait_for_load_state("domcontentloaded", timeout=60000)
    await page.wait_for_timeout(2000)

    # ─── 1. Biệt danh ───
    log.info(f"2. Điền Biệt danh: {nickname}")
    # Dùng JS để tìm input nickname vì selector có thể thay đổi
    nick_inp = None
    for sel in [
        "input[name='nickname']",
        "input#nickname",
        "input[name='nick_name']",
        "input[id*='nickname']",
        "input[name='nickName']",
        "input[placeholder*='ニック']",
        "input[placeholder*='Nick']",
        "td:has-text('ニックネーム') ~ td input",
        "tr:has-text('ニックネーム') input[type='text']",
        "input[type='text']:first-of-type",
    ]:
        try:
            el = await page.query_selector(sel)
            if el:
                nick_inp = el
                log.info(f"   Tìm thấy nickname input: {sel}")
                break
        except Exception:
            continue

    if nick_inp:
        await nick_inp.fill(nickname)
    else:
        raise ValueError(f"Không tìm thấy trường ニックネーム! URL: {page.url}")


    # ─── 2. Mật khẩu (2 lần) ───
    log.info("3. Điền Mật khẩu...")
    pass_inputs = await page.query_selector_all(
        "input[type='password'], input[name*='password'], input[id*='password'], input[name*='pass']"
    )
    if len(pass_inputs) >= 2:
        await pass_inputs[0].fill(password)
        await pass_inputs[0].evaluate("el => el.blur()")
        await pass_inputs[1].fill(password)
        await pass_inputs[1].evaluate("el => el.blur()")
        log.info("   Đã điền và blur 2 ô mật khẩu.")
    elif len(pass_inputs) == 1:
        await pass_inputs[0].fill(password)
        await pass_inputs[0].evaluate("el => el.blur()")
        log.warning("   Chỉ tìm thấy và blur 1 ô mật khẩu!")
    else:
        log.error("   Không tìm thấy ô mật khẩu!")

    # ─── 3. Giới tính ───
    gender_val = config.DEFAULT_GENDER
    log.info(f"4. Chọn Giới tính: {gender_val}")
    try:
        gender_select = await page.query_selector("select[name='gender'], select#gender")
        if gender_select:
            options = await gender_select.query_selector_all("option")
            for opt in options:
                opt_text = (await opt.inner_text()).strip()
                opt_value = await opt.get_attribute("value")
                if gender_val in opt_text or "回答" in opt_text:
                    await gender_select.select_option(opt_value)
                    log.info(f"   Đã chọn giới tính: {opt_text}")
                    break
        else:
            label = await page.query_selector(f"label:has-text('{gender_val}'), label:has-text('回答しない')")
            if label:
                await label.click()
    except Exception as e:
        log.warning(f"   Lỗi chọn giới tính: {e}")

    # ─── 4. Ngày sinh ───
    log.info(f"5. Chọn Ngày sinh: {birthday_str}")
    try:
        # Dump tất cả select để tìm đúng field name
        all_selects = await page.evaluate("""
            () => Array.from(document.querySelectorAll('select')).map(s => ({
                name: s.name, id: s.id, options: s.options.length
            }))
        """)
        log.info(f"   Dump selects: {all_selects}")

        # Tìm select year/month/day theo name
        year_sel = month_sel = day_sel = None
        for s in all_selects:
            n = (s.get("name") or "").lower()
            i = (s.get("id") or "").lower()
            key = n or i
            if "year" in key or "birth_y" in key or key.endswith("_y"):
                year_sel = f"select[name='{s['name']}']" if s.get("name") else f"select#{s['id']}"
            elif "month" in key or "birth_m" in key or key.endswith("_m"):
                month_sel = f"select[name='{s['name']}']" if s.get("name") else f"select#{s['id']}"
            elif "day" in key or "birth_d" in key or key.endswith("_d"):
                day_sel = f"select[name='{s['name']}']" if s.get("name") else f"select#{s['id']}"

        if year_sel:
            await page.select_option(year_sel, birth_year)
            log.info(f"   Năm sinh OK: {year_sel}")
        if month_sel:
            await page.select_option(month_sel, str(int(birth_month)))
            log.info(f"   Tháng sinh OK: {month_sel}")
        if day_sel:
            await page.select_option(day_sel, str(int(birth_day)))
            log.info(f"   Ngày sinh OK: {day_sel}")
        if not (year_sel or month_sel or day_sel):
            log.info("   Form Parks không có select DOB riêng — thử điền text input...")
            # Birthday là text input: BIRTH_YEAR, BIRTH_MONTH, BIRTH_DAY
            for fname, val in [("BIRTH_YEAR", birth_year), ("BIRTH_MONTH", str(int(birth_month))), ("BIRTH_DAY", str(int(birth_day)))]:
                try:
                    el = await page.query_selector(f"input[name='{fname}'], input#{fname}")
                    if el:
                        await el.fill(val)
                        log.info(f"   Điền {fname}={val} OK")
                except Exception as ex:
                    log.warning(f"   Không fill được {fname}: {ex}")
    except Exception as e:
        log.warning(f"   Lỗi chọn ngày sinh: {e}")

    # ─── 5. Tỉnh thành ───
    pref_val = prefecture
    log.info(f"6. Chọn Tỉnh thành: {pref_val}")
    try:
        all_selects2 = await page.evaluate("""
            () => Array.from(document.querySelectorAll('select')).map(s => ({
                name: s.name, id: s.id, options: s.options.length
            }))
        """)
        pref_sel_name = None
        for s in all_selects2:
            n = (s.get("name") or "").lower()
            i = (s.get("id") or "").lower()
            key = n or i
            # Nhận ADDR1 (Parks form), pref, prefecture, address, ken, area
            if any(k in key for k in ["pref", "address", "ken", "area", "addr"]):
                pref_sel_name = s["name"] or s["id"]
                log.info(f"   Tìm thấy select tỉnh thành: name='{pref_sel_name}' options={s['options']}")
                break
        if pref_sel_name:
            pref_sel_el = await page.query_selector(f"select[name='{pref_sel_name}'], select#{pref_sel_name}")
            options = await pref_sel_el.query_selector_all("option")
            for opt in options:
                opt_text = (await opt.inner_text()).strip()
                opt_val = await opt.get_attribute("value")
                if pref_val in opt_text:
                    await pref_sel_el.select_option(opt_val)
                    log.info(f"   Tỉnh thành OK: {pref_val} (name={pref_sel_name})")
                    break
        else:
            log.warning(f"   Không tìm thấy select tỉnh thành. Selects: {all_selects2}")
    except Exception as e:
        log.warning(f"   Lỗi chọn tỉnh thành: {e}")



    # ─── 7. Thuê số điện thoại ───
    if not config.SMS_ENABLED:
        log.warning("⚠️ SMS_ENABLED=false. Dừng để nhập số thủ công...")
        await asyncio.to_thread(input, "Nhấn Enter sau khi đã điền số điện thoại...")
        return "MANUAL", "MANUAL"

    log.info("8. Thuê số điện thoại Nhật Bản và submit form...")
    phone = None
    pkey = None

    for phone_attempt in range(4):  # Tối đa 4 số nếu bị lỗi
        log.info(f"   [Phone attempt {phone_attempt+1}/4] Đảm bảo ở trang form đăng ký...")

        # Đảm bảo ta đang ở trang điền form (có input TEL) trước khi thuê số!
        tel_inp = await page.query_selector("input[name='TEL'], input#TEL, input[name='tel'], input#tel")
        if not tel_inp:
            log.info("   Không tìm thấy input TEL. Có thể đang ở trang xác nhận hoặc trang lỗi. Thử click button quay lại...")
            back_clicked = False
            for back_sel in [
                "button:has-text('戻る')",
                "button:has-text('修正する')",
                "input[type='button'][value*='戻る']",
                "input[type='button'][value*='修正']",
                "a:has-text('戻る')",
                "a:has-text('修正')",
                ".btn-back",
                "#btn-back",
            ]:
                try:
                    btn = await page.query_selector(back_sel)
                    if btn and await btn.is_visible():
                        log.info(f"   Click nút quay lại: {back_sel}")
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        back_clicked = True
                        break
                except Exception:
                    continue

            if not back_clicked:
                log.info("   Không thấy nút quay lại trên trang. Thử page.go_back()...")
                await page.go_back()
                await page.wait_for_timeout(2000)

            # Kiểm tra lại sau khi go back/click quay lại
            tel_inp = await page.query_selector("input[name='TEL'], input#TEL, input[name='tel'], input#tel")
            if not tel_inp:
                log.warning("   Vẫn không thấy input TEL. Load lại trang form mới...")
                await page.goto(
                    "https://parks2.bandainamco-am.co.jp/member_regist_new.html",
                    wait_until="commit",
                    timeout=90000,
                )
                await page.wait_for_timeout(2000)
                tel_inp = await page.query_selector("input[name='TEL'], input#TEL, input[name='tel'], input#tel")

        if not tel_inp:
            raise ValueError("Không tìm thấy input TEL trong form Parks!")

        log.info("   Order số mới...")
        try:
            order = sms_service.order_phone()
            raw_phone = order["phone"]
            pkey = order["pkey"]
            phone = format_jp_phone(raw_phone)
            log.info(f"   Thuê: {raw_phone} → {phone} | PKey: {pkey[:12]}...")
        except Exception as order_err:
            log.warning(f"   ⚠️ Lỗi khi order số điện thoại từ API: {order_err}. Đợi 10 giây và thuê lại số khác...")
            await page.wait_for_timeout(10000)
            continue


        # Clear rồi mới fill để tránh trạng thái lỗi cũ còn sót
        await tel_inp.fill("")
        await page.wait_for_timeout(300)
        await tel_inp.fill(phone)
        await tel_inp.evaluate("el => el.dispatchEvent(new Event('change', {bubbles:true}))")
        await page.wait_for_timeout(500)
        log.info(f"   Phone fill OK: {phone}")

        # Tick checkbox điều khoản (mỗi lần retry đều phải tick lại)
        agree_cbs = await page.query_selector_all("input[type='checkbox']")
        ticked = 0
        for cb in agree_cbs:
            await cb.evaluate("el => { if (!el.checked) el.click(); }")
            ticked += 1
        log.info(f"   Đã tick {ticked} checkbox.")

        # Click 入力内容を確認する — chờ button enabled (không disabled)
        log.info("   Click '入力内容を確認する'...")
        await page.wait_for_timeout(500)
        confirm_btn = await page.wait_for_selector(
            "button:has-text('入力内容を確認する'), input[type='submit'][value*='確認'], a:has-text('確認')",
            timeout=60000,
            state="visible",
        )
        await confirm_btn.scroll_into_view_if_needed()
        await page.wait_for_timeout(500)
        await confirm_btn.click()
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            pass
        await page.wait_for_timeout(1500)
        log.info(f"   Trang xác nhận: {page.url}")

        # Dump tất cả button/submit trên confirmation page để debug
        all_btns = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button, input[type="submit"], a[href]')).map(el => ({
                tag: el.tagName, text: el.innerText || el.value || '', type: el.type || '',
                href: el.href || '', disabled: el.disabled
            })).filter(el => el.text.trim().length > 0)
        """)
        log.info(f"   Buttons trên confirmation page: {all_btns}")

        # Click 登録する — thử nhiều selector, cuối cùng fallback JS submit
        log.info("   Click '登録する'...")
        submit_sel = (
            "button:has-text('登録する'), button:has-text('送信する'), "
            "button:has-text('この内容で登録'), "
            "input[type='submit'][value*='登録'], input[type='submit'][value*='送信'], "
            "input[type='submit']:not([value])"
        )
        submit_btn = None
        try:
            submit_btn = await page.wait_for_selector(submit_sel, timeout=30000, state="visible")
        except Exception:
            log.warning("   selector thông thường timeout — thử click button cuối cùng trong form...")
            try:
                # Fallback: JS click vào button submit cuối cùng
                await page.evaluate("""
                    () => {
                        const btns = [...document.querySelectorAll('button, input[type="submit"]')];
                        const last = btns[btns.length - 1];
                        if (last) last.click();
                    }
                """)
                await page.wait_for_load_state("domcontentloaded", timeout=20000)
                log.info("   JS fallback click done.")
            except Exception as je:
                log.warning(f"   JS fallback lỗi: {je}")

        if submit_btn:
            await submit_btn.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)
            await submit_btn.click()
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass

        await page.wait_for_timeout(2000)
        log.info(f"   URL sau submit: {page.url}")

        # Kiểm tra lỗi về số điện thoại sau khi trang reload
        page_text = await page.evaluate("() => document.body.innerText")
        phone_errors = [
            "既に使用",           # đã được sử dụng
            "使用されています",     # đã được sử dụng (dạng khác)
            "already in use",
            "不正な電話番号",       # số không hợp lệ
            "invalid phone",
            "電話番号が正しくありません",  # số không đúng
            "入力した電話番号",     # bất kỳ lỗi về phone input
        ]
        phone_ok = not any(err in page_text for err in phone_errors)

        if phone_ok:
            log.info(f"   ✅ Số {phone} hợp lệ, đã submit thành công.")
            break
        else:
            # Tìm text lỗi cụ thể để log
            err_found = [e for e in phone_errors if e in page_text]
            log.warning(f"   Số {phone} bị lỗi [{err_found}]. Hủy và thử số mới...")
            try:
                sms_service.cancel(pkey)
                log.info(f"   Đã hủy số {phone}.")
            except Exception as ce:
                log.warning(f"   Không hủy được số: {ce}")
            phone = None
            pkey = None
            # Quay lại trang form nếu chưa ở trang form (có input TEL)
            has_tel = await page.query_selector("input[name='TEL'], input#TEL, input[name='tel'], input#tel")
            if not has_tel:
                log.info("   Chưa quay lại trang form. Thực hiện go_back...")
                await page.go_back()
                await page.wait_for_load_state("domcontentloaded", timeout=60000)
            continue

    if not phone or not pkey:
        raise ValueError("Không thể thuê được số điện thoại hợp lệ sau 4 lần thử!")

    log.info(f"   ✅ Kích hoạt SMS OTP. URL: {page.url}")
    return phone, pkey
