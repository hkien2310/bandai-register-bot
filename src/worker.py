import asyncio
import traceback
import src.config as config
import csv
from queue import Queue, Empty
from src.core.browser import BrowserInstance
from src.flows.step1_connect import run_step1
from src.flows.step2_bnid_click import run_step2
from src.flows.step3_bnid_register import run_step3
from src.flows.step4_parks_profile import run_step4
from src.flows.step5_sms_verification import run_step5
from src.utils.data_gen import generate_birthday, generate_nickname, generate_password
from src.utils.logger import get_logger, set_worker_prefix


log = get_logger("worker")

class RegistrationWorker:
    def __init__(self, worker_id: int, email_queue: Queue, proxy_pool, sheets_manager):
        self.worker_id = worker_id
        self.email_queue = email_queue
        self.proxy_pool = proxy_pool
        self.sheets_manager = sheets_manager

    def run(self):
        """Hàm chạy của luồng Thread."""
        set_worker_prefix(f"Worker-{self.worker_id}")
        log.info("Worker started.")
        
        while True:
            if config.STOP_FLAG:
                log.warning("🛑 Nhận lệnh STOP, worker kết thúc.")
                break

            try:
                # Lấy email từ queue, timeout 5 giây để thoát nếu hết hàng
                email_data = self.email_queue.get(timeout=5)
                email = email_data["email"]
                email_password = email_data.get("email_password", "")
                raw_email = email_data.get("raw_email", email)
            except Empty:
                log.info("Queue trống. Worker kết thúc.")
                break
                
            short_email = email.split("@")[0] if "@" in email else email
            set_worker_prefix(f"Worker-{self.worker_id} | {short_email}")

            # Sinh/đọc dữ liệu
            password = generate_password(email)
            
            # Đọc ngày tháng năm sinh (ưu tiên từ Sheet Mails, nếu không có thì dùng config.DEFAULT_DOB, nếu không có nữa thì sinh ngẫu nhiên)
            dob_from_sheet = email_data.get("dob", "").strip()
            if dob_from_sheet:
                birthday = dob_from_sheet
            elif config.DEFAULT_DOB:
                birthday = config.DEFAULT_DOB
            else:
                birthday = generate_birthday(email)
                
            # Đọc tỉnh thành (ưu tiên từ Sheet Mails, nếu không có thì dùng config.DEFAULT_PREFECTURE)
            prefecture = email_data.get("prefecture", "").strip()
            if not prefecture:
                prefecture = config.DEFAULT_PREFECTURE

            VALID_PREFECTURES = [
                "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", 
                "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県", 
                "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", 
                "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県", 
                "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県", 
                "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県", 
                "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"
            ]

            nickname_from_sheet = email_data.get("nickname", "").strip()
            if nickname_from_sheet:
                nickname = nickname_from_sheet
            elif getattr(config, "DEFAULT_NICKNAME", ""):
                nickname = config.DEFAULT_NICKNAME
            else:
                nickname = generate_nickname(email)
            
            # Khởi tạo thông tin ghi kết quả ban đầu
            result_data = {
                "email": email,
                "bandai_password": password,
                "namco_password": password,
                "nickname": nickname,
                "dob": birthday,
                "prefecture": prefecture,
                "phone": "",
                "bnid_user_code": "",
                "proxy_used": "",
                "status": "PROCESSING",
                "error_details": ""
            }
            
            # Đánh dấu PROCESSING lên Sheet Mails ngay khi worker thực sự bắt đầu làm
            self.sheets_manager.update_email_status(raw_email, "PROCESSING")
            # Ghi record ban đầu vào Accounts ngay để hiện thị kết quả real-time
            self.sheets_manager.append_account(result_data)

            if prefecture and prefecture not in VALID_PREFECTURES:
                error_msg = f"Tỉnh thành '{prefecture}' không hợp lệ. Vui lòng nhập đúng tỉnh thành của Nhật Bản."
                log.error(f"❌ {error_msg}")
                result_data["status"] = "ERROR"
                result_data["error_details"] = error_msg
                self.sheets_manager.update_email_status(raw_email, "ERROR")
                self.sheets_manager.append_account(result_data)
                self.queue_processor.on_task_done()
                continue

            # Kiểm tra trên Sheet Accounts xem email này đã có BNID chưa
            existing_status = self.sheets_manager.get_account_status(email)
            has_bnid_local = existing_status in ("HAS_BNID",)
            if has_bnid_local:
                log.info(f"📋 Sheet Accounts cho thấy {email} đã có BNID (status={existing_status}). Sẽ chạy luồng LOGIN.")
            
            # Chỉ thử 1 lần cho mỗi lượt chạy. Lỗi thì chuyển sang account tiếp theo luôn.
            max_retries = 1
            success = False
            for attempt in range(1, max_retries + 1):
                if config.STOP_FLAG:
                    log.warning("🛑 Nhận lệnh STOP, hủy bỏ proxy check.")
                    break

                proxy = None
                proxy_idx = -1
                proxy_str = "Direct"
                
                # Tìm và kiểm tra proxy sống trước khi bắt đầu flow
                import requests
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                
                proxy, proxy_idx = None, -1
                proxy_str = "Direct"
                if config.USE_PROXY:
                    proxy_attempts = 0
                    max_proxy_attempts = 3
                    
                    while proxy_attempts < max_proxy_attempts:
                        proxy_attempts += 1
                        proxy, proxy_idx = self.proxy_pool.get_next_proxy()
                        proxy_str = proxy["raw"] if proxy else "Direct"
                        
                        if not proxy:
                            log.error("❌ KHO PROXY ĐÃ CẠN KIỆT (CHẾT CHÙM). TẠM DỪNG TOÀN BỘ!")
                            with self.email_queue.mutex:
                                self.email_queue.queue.clear()
                            break  # Hết proxy
                            
                        log.info(f"🔄 Đang kiểm tra proxy ({proxy_attempts}/{max_proxy_attempts}): {proxy_str}...")
                        requests_proxy = proxy_str
                        # Chuyển đổi format "http://host:port:user:pass" sang "http://user:pass@host:port" cho requests
                        if proxy_str:
                            p_parts = proxy_str.replace("http://", "").replace("https://", "").split(":")
                            if len(p_parts) == 4:
                                requests_proxy = f"http://{p_parts[2]}:{p_parts[3]}@{p_parts[0]}:{p_parts[1]}"
                                
                        proxies_dict = {
                            "http": requests_proxy,
                            "https": requests_proxy
                        }
                        try:
                            r = requests.get("https://parks2.bandainamco-am.co.jp/", proxies=proxies_dict, timeout=10, verify=False)
                            if "アクセス集中" in r.text or "エラーが発生しました" in r.text:
                                raise Exception("SITE_OVERLOADED")
                            
                            r.raise_for_status()
                            log.info(f"✅ Proxy còn sống và truy cập được Namco Parks!")
                            break
                        except Exception as e:
                            if "SITE_OVERLOADED" in str(e) or (hasattr(e, 'response') and e.response is not None and e.response.status_code in [502, 503, 504]):
                                raise Exception("SITE_OVERLOADED: Namco server quá tải ngay bước check proxy!")
                                
                            log.warning(f"❌ Proxy chết ({type(e).__name__}), đổi proxy khác...")
                            self.proxy_pool.mark_failed(proxy_idx)
                            proxy = None  # Đặt lại None để báo hiệu chưa có proxy sống
                else:
                    log.info("⚠️ Chạy KHÔNG DÙNG PROXY theo cấu hình (USE_PROXY=false)")
                
                result_data["proxy_used"] = proxy_str
                
                log.info(f"🚀 [Attempt {attempt}/{max_retries}] Bắt đầu xử lý: {email} | Proxy: {proxy_str} | HasBNID: {has_bnid_local} | DOB: {birthday} | Location: {prefecture}")
                
                # Cập nhật status lên sheet Mails (dùng raw_email để match dòng trên Sheet)
                result_data["status"] = "PROCESSING"
                self.sheets_manager.update_email_status(raw_email, "PROCESSING")
                
                try:
                    if config.USE_PROXY and not proxy:
                        if len(self.proxy_pool.proxies) == 0:
                            raise Exception("KHO_PROXY_CAN_KIET")
                        else:
                            raise Exception("Không tìm được proxy sống sau 3 lần thử.")
                    try:
                        asyncio.run(asyncio.wait_for(
                            self._process_account_async(email, password, nickname, birthday, prefecture, proxy, result_data, has_bnid_local, email_password, email_data.get("ms_token", ""), email_data.get("ms_uuid", "")),
                            timeout=300
                        ))
                        # Nếu thành công
                        has_bnid_local = True
                        success = True
                    except asyncio.TimeoutError:
                        log.error(f"❌ Tài khoản {email} bị treo (vượt quá 5 phút). Tự động dừng luồng này và bỏ qua.")
                        self.sheets_manager.update_email_status(raw_email, "ERROR")
                        result_data["status"] = "ERROR"
                        result_data["error_details"] = "Timeout/Hanging"
                        self.sheets_manager.append_account(result_data)
                    except BaseException as e:
                        raise e
                    self.proxy_pool.mark_used(proxy_idx)
                    break
                except Exception as e:
                    error_msg = str(e)
                    log.warning(f"⚠️ [Attempt {attempt} Thất bại] Lỗi khi xử lý {email}: {error_msg}")
                    
                    # ─── Lỗi cạn kiệt proxy ───
                    if "KHO_PROXY_CAN_KIET" in error_msg:
                        log.warning("Hoàn trả account về PENDING do proxy cạn kiệt trước khi chạy.")
                        result_data["status"] = "PENDING"
                        result_data["error_details"] = "Proxy pool cạn kiệt"
                        break

                    # ─── Lỗi quá tải Server Namco ───
                    if "SITE_OVERLOADED" in error_msg:
                        log.error("❌ Server Namco đang quá tải (アクセス集中). TỰ ĐỘNG DỪNG TOOL và ghi kết quả thất bại lên Sheet.")
                        result_data["status"] = "FAILED"
                        result_data["error_details"] = "Server Namco quá tải (Access Concentration)"
                        self.proxy_pool.mark_used(proxy_idx)
                        config.STOP_FLAG = True  # Phát tín hiệu dừng toàn bộ bot
                        break

                    if config.STOP_FLAG:
                        log.warning("🛑 Nhận lệnh STOP, huỷ bỏ xử lý lỗi và thoát luồng.")
                        result_data["status"] = "ABORTED"
                        result_data["error_details"] = "Dừng đột ngột"
                        self.proxy_pool.mark_used(proxy_idx)
                        break
                        
                    # ─── Phân loại lỗi: KHÔNG RETRY vs CÓ THỂ RETRY ───
                    NO_RETRY_KEYWORDS = [
                        "EMAIL_ALREADY_IN_USE",          # Email đã đăng ký rồi
                        "Email đã được sử dụng",         # Thông báo tiếng Việt
                        "KeyboardInterrupt",             # User tự tắt
                    ]
                    is_permanent = any(kw in error_msg for kw in NO_RETRY_KEYWORDS)
                    
                    if is_permanent:
                        log.error(f"🚫 Lỗi KHÔNG THỂ RETRY: {error_msg[:200]}")
                        if "EMAIL_ALREADY_IN_USE" in error_msg or "Email đã được sử dụng" in error_msg:
                            result_data["status"] = "HAS_BNID"
                        else:
                            result_data["status"] = "ABORTED"
                        result_data["error_details"] = error_msg[:200]
                        self.proxy_pool.mark_used(proxy_idx)
                        break  # Thoát vòng retry ngay
                    
                    # ─── Lỗi CÓ THỂ RETRY ───
                    # Đánh dấu proxy chết nếu lỗi mạng
                    is_proxy_error = False
                    if "net::ERR_" in error_msg or "Target page, context or browser has been closed" in error_msg or "Timeout" in error_msg:
                        log.warning(f"   -> Lỗi mạng/trình duyệt, đánh dấu proxy chết...")
                        self.proxy_pool.mark_failed(proxy_idx)
                        is_proxy_error = True
                    
                    if result_data["bnid_user_code"] != "":
                        log.info("   -> Đã tạo BNID thành công nhưng lỗi ở bước sau. Đánh dấu HAS_BNID và bỏ qua không thử lại.")
                        result_data["status"] = "HAS_BNID"
                        self.proxy_pool.mark_used(proxy_idx)
                        break

                    result_data["status"] = "FAILED"
                    result_data["error_details"] = error_msg[:200]
                        
                    if attempt == max_retries:
                        log.error(f"❌ Đã thử {max_retries} lần đều thất bại cho {email}")
                        if not is_proxy_error:
                            self.proxy_pool.mark_used(proxy_idx)
                        break
                    else:
                        # MỞ KHÓA proxy trước khi retry để worker khác có thể dùng
                        self.proxy_pool.release_proxy(proxy_idx)
                        log.info("⏳ Lỗi có thể retry. Thử lại sau 2 giây...")
                        import time
                        # Chờ ngắt quãng để phản hồi STOP ngay lập tức
                        for _ in range(4):
                            if config.STOP_FLAG: break
                            time.sleep(0.5)

            # MỞ KHÓA proxy sau khi xử lý xong account (dù thành công hay thất bại)
            self.proxy_pool.release_proxy(proxy_idx)

            # Kết quả cuối cùng — luôn ghi vào Accounts (upsert)
            self.sheets_manager.update_email_status(raw_email, result_data["status"])
            self.sheets_manager.append_account(result_data)
            self.email_queue.task_done()
            log.info(f"Kết thúc xử lý tài khoản {email}\n" + "-"*50)

            if config.STOP_FLAG:
                log.warning("🛑 Nhận lệnh STOP hoặc kịch bản dừng (như quá tải), kết thúc luồng.")
                break

    async def _process_account_async(self, email, password, nickname, birthday, prefecture, proxy, result_data, has_bnid_local, email_password: str = "", refresh_token: str = "", client_id: str = ""):
        """Chạy các bước đăng ký tuần tự trong cùng một event loop."""
        browser = BrowserInstance(worker_id=self.worker_id, proxy=proxy)
        try:
            page = await browser.start()

            # ═══════════════════════════════════════════════
            # CÁC BƯỚC ĐĂNG KÝ / ĐĂNG NHẬP
            # ═══════════════════════════════════════════════

            if config.STOP_FLAG: raise Exception("KeyboardInterrupt")

            # Step 1: Vào trang chủ + Click link đăng ký
            try:
                await run_step1(page)
            except Exception as e:
                raise Exception(f"Lỗi Bước 1 (Vào trang chủ): {str(e).split('Call log')[0].strip()}")

            # Step 2: Click nút vàng Get BNID
            if config.STOP_FLAG: raise Exception("KeyboardInterrupt")
            try:
                await run_step2(page, has_bnid=has_bnid_local)
            except Exception as e:
                raise Exception(f"Lỗi Bước 2 (Click nút Get BNID): {str(e).split('Call log')[0].strip()}")

            # Step 3: Đăng ký BNID + Nhập OTP Email
            if config.STOP_FLAG: raise Exception("KeyboardInterrupt")
            try:
                await run_step3(
                    page=page, 
                    email=email, 
                    password=password, 
                    birthday=birthday, 
                    has_bnid=has_bnid_local, 
                    email_password=email_password,
                    refresh_token=refresh_token,
                    client_id=client_id
                )
                result_data["bnid_user_code"] = "TRUE"
                log.info(f"✅ Step 3 done — Đã qua bước OTP Email, đặt BNID = TRUE")
                # Ghi ngay vào Accounts sau khi OTP email thành công
                self.sheets_manager.append_account(result_data)
            except Exception as e:
                err = str(e)
                if "Không nhận được OTP email" in err:
                    raise Exception("Lỗi Bước 3 (OTP Email): Không nhận được OTP từ Bandai Namco sau 120s.")
                elif "EMAIL_ALREADY_IN_USE" in err:
                    raise Exception("Lỗi Bước 3 (Tạo BNID): Email đã được sử dụng.")
                else:
                    raise Exception(f"Lỗi Bước 3 (Tạo BNID): Mạng chậm hoặc web thay đổi ({err.split('Call log')[0].strip()})")

            # Step 4: Điền Profile Namco Parks + Thuê số điện thoại
            if config.STOP_FLAG: raise Exception("KeyboardInterrupt")
            try:
                step4_result = await run_step4(page, email, password, nickname, birthday, prefecture)
                phone, pkey = step4_result  # run_step4 luôn trả tuple (phone, pkey)
                
                if phone == "ALREADY_REGISTERED":
                    log.info(f"🎉 Tài khoản {email} đã được liên kết Namco Parks và xác thực SĐT trước đó.")
                    result_data["status"] = "SUCCESS"
                    result_data["error_details"] = "Đã liên kết Namco Parks từ trước"
                    return  # Kết thúc sớm

                result_data["phone"] = phone
                log.info(f"✅ Step 4 done — Phone: {phone}")
                # (Không cần append giữa chừng)
            except Exception as e:
                raise Exception(f"Lỗi Bước 4 (Điền Profile): {str(e).split('Call log')[0].strip()}")

            # Step 5: Xác thực SMS OTP
            if config.STOP_FLAG: raise Exception("KeyboardInterrupt")
            try:
                await run_step5(page, phone, pkey)
                log.info("✅ Step 5 done — SMS Verified successfully")
            except Exception as e:
                err = str(e)
                if "SMS_OTP_TIMEOUT" in err:
                    raise Exception(f"Lỗi Bước 5 (Xác thực SMS): Không nhận được OTP từ API (SĐT: {phone})")
                else:
                    raise Exception(f"Lỗi Bước 5 (Xác thực SMS): {err.split('Call log')[0].strip()}")

            # ═══════════════════════════════════════════════
            # HOÀN THÀNH — Đánh dấu SUCCESS
            # ═══════════════════════════════════════════════
            result_data["status"] = "SUCCESS"

            # Lấy BNID từ portal nếu step 3 không bóc được
            if not result_data.get("bnid_user_code"):
                import re as _re
                async def _try_extract_bnid(url: str) -> str | None:
                    try:
                        await page.goto(url, timeout=20000)
                        await page.wait_for_load_state("domcontentloaded")
                        await asyncio.sleep(2)
                        html = await page.evaluate("() => document.body ? document.body.innerHTML : ''")
                        # BNID thường có dạng B + 12 số (vd: B999888777666) hoặc 12 số
                        m = _re.search(r'\b(B\d{12}|\d{12})\b', html)
                        if m:
                            bnid = m.group(1).strip()
                            log.info(f"🔍 [{url}] Tìm thấy chuỗi nghi ngờ BNID trong HTML: {bnid}")
                            return bnid
                        else:
                            text_preview = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 300) : ''")
                            log.info(f"🔍 [{url}] Không tìm thấy BNID. Text preview: {text_preview}")
                    except Exception as ex:
                        log.warning(f"⚠️ Lỗi truy cập {url}: {ex}")
                    return None

                log.info("🔍 Thử lấy BNID từ portal BNID...")
                bnid_code = await _try_extract_bnid("https://account.bandainamcoid.com/portal.html")
                if not bnid_code:
                    log.info("🔍 Thử lấy BNID từ Namco Parks mypage...")
                    bnid_code = await _try_extract_bnid("https://parks2.bandainamco-am.co.jp/member_mypage.html")
                if bnid_code:
                    log.info(f"✅ Đã lấy được BNID User Code: {bnid_code}")
                    result_data["bnid_user_code"] = bnid_code
                    self.sheets_manager.append_account(result_data)
                else:
                    log.warning("⚠️ Không tìm thấy BNID User Code ở cả portal lẫn mypage.")

            log.info(f"✅ Đăng ký thành công cho tài khoản {email}")


        except Exception as e:
            # Chụp screenshot lỗi nếu trình duyệt vẫn đang chạy
            is_overloaded = False
            if browser and browser.context:
                try:
                    if browser.context.pages:
                        page = browser.context.pages[0]
                        # Kiểm tra xem trang có báo lỗi quá tải không
                        try:
                            body_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
                            if "アクセス集中" in body_text or "エラーが発生しました" in body_text:
                                is_overloaded = True
                        except:
                            pass

                        if not config.STOP_FLAG:
                            screenshot_path = str(config.DATA_DIR / f"error_fatal_{email.replace('+', '_')}.png")
                            await asyncio.wait_for(page.screenshot(path=screenshot_path), timeout=5.0)
                            log.info(f"Đã chụp screenshot lỗi fatal: {screenshot_path}")
                except Exception as se:
                    log.debug(f"Không thể chụp screenshot lỗi fatal: {se}")
                    
            if is_overloaded:
                raise Exception("SITE_OVERLOADED: Trang web Namco đang bị quá tải (Access Concentration).")
            raise e
        finally:
            # Giữ browser mở để quan sát nếu KEEP_BROWSER_OPEN=true
            if config.KEEP_BROWSER_OPEN and browser and browser.context:
                log.info("⏸️  KEEP_BROWSER_OPEN=true — Giữ browser mở. Nhấn [ENTER] để đóng...")
                await asyncio.to_thread(input, "")
            # Đóng browser và xóa data
            if browser:
                usage_mb = browser.get_data_usage_mb()
                result_data["data_usage_mb"] = round(usage_mb, 2)
                log.info(f"📊 Tổng dữ liệu đã tiêu thụ (tải về + tải lên): {usage_mb:.2f} MB")
                await browser.close()
