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

    def _finish_task(self, status):
        config.SESSION_STATS["PROCESSING"] = max(0, config.SESSION_STATS["PROCESSING"] - 1)
        if status == "SUCCESS":
            config.SESSION_STATS["SUCCESS"] += 1
        elif status == "FAIL_NO_RETRY":
            config.SESSION_STATS["FAIL_NO_RETRY"] = config.SESSION_STATS.get("FAIL_NO_RETRY", 0) + 1
        elif status in ("FAILED", "ERROR"):
            config.SESSION_STATS["FAILED"] += 1
        elif status == "PENDING":
            config.SESSION_STATS["PENDING"] += 1
        elif status == "HAS_BNID":
            config.SESSION_STATS["HAS_BNID"] = config.SESSION_STATS.get("HAS_BNID", 0) + 1
        self.email_queue.task_done()

    def run(self):
        """Hàm chạy của luồng Thread."""
        set_worker_prefix(f"Worker-{self.worker_id}")
        log.info("Worker started.")
        
        import time, random
        delay_time = random.uniform(1.0, 3.0) * self.worker_id
        if delay_time > 0:
            log.info(f"⏳ Đợi {delay_time:.1f}s trước khi bắt đầu (giãn cách các luồng khởi động)...")
            time.sleep(delay_time)
        
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
                
                config.SESSION_STATS["PENDING"] = max(0, config.SESSION_STATS["PENDING"] - 1)
                config.SESSION_STATS["PROCESSING"] += 1
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
                self._finish_task(result_data["status"])
                continue

            # Kiểm tra HAS_BNID: ưu tiên status từ Mails sheet, fallback check Accounts sheet
            mail_status = email_data.get("mail_status", "").strip().upper()
            account_info = self.sheets_manager.get_account_info(email)
            existing_status = account_info.get("status", "")
            has_bnid_local = mail_status == "HAS_BNID" or existing_status == "HAS_BNID"
            if has_bnid_local:
                # Lấy mật khẩu BNID từ Accounts, nếu không có thì giữ password mặc định
                saved_password = account_info.get("bandai_password", "").strip()
                if saved_password:
                    password = saved_password
                    result_data["bandai_password"] = password
                    result_data["namco_password"] = password
                    log.info(f"📋 HAS_BNID: Dùng password '{password}' từ Accounts cho {email}. Chạy luồng LOGIN.")
                else:
                    log.info(f"📋 HAS_BNID: Không có password trong Accounts, dùng password mặc định '{password}'. Chạy luồng LOGIN.")
            
            # Chỉ thử 1 lần cho mỗi lượt chạy. Lỗi thì chuyển sang account tiếp theo luôn.
            max_retries = 1
            success = False
            for attempt in range(1, max_retries + 1):
                if config.STOP_FLAG:
                    result_data["status"] = "PENDING"
                    result_data["error_details"] = "Dừng đột ngột"
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
                proxy_overloaded = False
                if config.USE_PROXY:
                    proxy_attempts = 0
                    max_proxy_attempts = 3
                    
                    while proxy_attempts < max_proxy_attempts:
                        proxy_attempts += 1
                        proxy, proxy_idx = self.proxy_pool.get_next_proxy()
                        
                        if proxy == "WAIT":
                            log.info("⏳ Tất cả proxy đang được sử dụng. Chờ 5s...")
                            import time
                            for _ in range(10):
                                if config.STOP_FLAG: break
                                time.sleep(0.5)
                            proxy_attempts -= 1  # Không tính lượt retry này
                            continue
                            
                        proxy_str = proxy["raw"] if proxy else "Direct"
                        
                        if not proxy:
                            log.error("❌ KHO PROXY ĐÃ CẠN KIỆT (CHẾT CHÙM).")
                            break  # Hết proxy, sẽ raise exception bên dưới
                            
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
                            if "アクセス集中" in r.text:
                                raise Exception("SITE_OVERLOADED")
                            if "Access Denied" in r.text or "access denied" in r.text.lower() or "エラーが発生しました" in r.text:
                                raise Exception("IP_BANNED")
                            
                            r.raise_for_status()
                            log.info(f"✅ Proxy còn sống và truy cập được Namco Parks!")
                            break
                        except Exception as e:
                            if "SITE_OVERLOADED" in str(e):
                                log.error(f"❌ Server Namco đang quá tải (アクセス集中). Tạm thời đánh dấu account này PENDING.")
                                self.sheets_manager.update_email_status(raw_email, "PENDING")
                                proxy_overloaded = True
                                break
                                
                            log.warning(f"❌ Proxy chết ({type(e).__name__}), đổi proxy khác...")
                            if proxy_idx >= 0:
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
                    if proxy_overloaded:
                        raise Exception("SITE_OVERLOADED")
                    
                    if config.USE_PROXY and not proxy:
                        if len(self.proxy_pool.proxies) == 0:
                            result_data["status"] = "FAILED"
                            result_data["error_details"] = "Kho proxy cạn kiệt"
                            raise Exception("KHO_PROXY_CAN_KIET")
                        else:
                            result_data["status"] = "FAILED"
                            result_data["error_details"] = "Không tìm được proxy sống sau 3 lần thử."
                            raise Exception("Không tìm được proxy sống sau 3 lần thử.")
                    try:
                        if not hasattr(config, "ACTIVE_WORKERS"):
                            config.ACTIVE_WORKERS = []
                        
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        task = loop.create_task(
                            asyncio.wait_for(
                                self._process_account_async(
                                    email, password, nickname, birthday, prefecture, proxy, result_data, has_bnid_local,
                                    email_password,
                                    email_data.get("ms_token", ""),
                                    email_data.get("ms_uuid", ""),
                                    email_data.get("otp_email", ""),
                                    email_data.get("otp_pass", ""),
                                    email_data.get("provider", "")
                                ),
                                timeout=600
                            )
                        )
                        
                        worker_info = {"loop": loop, "task": task}
                        config.ACTIVE_WORKERS.append(worker_info)
                        
                        try:
                            loop.run_until_complete(task)
                        finally:
                            if worker_info in config.ACTIVE_WORKERS:
                                config.ACTIVE_WORKERS.remove(worker_info)
                            loop.close()
                            
                        # Nếu thành công
                        has_bnid_local = True
                        success = True
                    except asyncio.TimeoutError:
                        log.error(f"❌ Tài khoản {email} bị treo (vượt quá 5 phút). Tự động dừng luồng này và bỏ qua.")
                        self.sheets_manager.update_email_status(raw_email, "ERROR")
                        result_data["status"] = "ERROR"
                        result_data["error_details"] = "Timeout/Hanging"
                        self.sheets_manager.append_account(result_data)
                    except asyncio.CancelledError:
                        log.warning(f"🛑 Tài khoản {email} bị huỷ đột ngột (User bấm Stop).")
                        result_data["status"] = "PENDING"
                        result_data["error_details"] = "Dừng đột ngột"
                        if proxy_idx >= 0:
                            self.proxy_pool.release_proxy(proxy_idx)
                        break
                    except BaseException as e:
                        raise e
                    if proxy_idx >= 0:
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
                        log.warning(f"❌ Server Namco đang quá tải hoặc lỗi hệ thống. Tự động bỏ qua account này và chuyển trạng thái thành FAILED.")
                        result_data["status"] = "FAILED"
                        result_data["error_details"] = "Server Namco quá tải hoặc lỗi hệ thống"
                        if proxy_idx >= 0:
                            self.proxy_pool.release_proxy(proxy_idx)
                        break

                    # ─── Lỗi Band IP ───
                    if "IP_BANNED" in error_msg or "Access Denied" in error_msg:
                        if not config.USE_PROXY:
                            log.warning("🚫 BỊ CHẶN IP KHI CHẠY KHÔNG DÙNG PROXY! (Đã tắt sleep 15m theo yêu cầu)")
                            result_data["status"] = "FAILED"
                            result_data["error_details"] = "IP bị chặn (Không dùng proxy)"
                            self.sheets_manager.update_email_status(raw_email, "FAILED")
                            break
                        else:
                            log.warning("❌ Proxy bị Ban IP. Đánh dấu chết và chuyển proxy khác...")
                            if proxy_idx >= 0:
                                self.proxy_pool.mark_failed(proxy_idx)
                            # Đẩy xuống dưới để tiếp tục vòng lặp retry với proxy mới
                            # Gán error để bên dưới mark is_proxy_error = True
                            error_msg += " net::ERR_PROXY_BANNED"

                    if config.STOP_FLAG:
                        log.warning("🛑 Nhận lệnh STOP, huỷ bỏ xử lý lỗi và thoát luồng.")
                        result_data["status"] = "PENDING"
                        result_data["error_details"] = "Dừng đột ngột"
                        if proxy_idx >= 0:
                            self.proxy_pool.release_proxy(proxy_idx)
                        break
                        
                    # ─── Phân loại lỗi: KHÔNG RETRY vs CÓ THỂ RETRY ───
                    NO_RETRY_KEYWORDS = [
                        "EMAIL_ALREADY_IN_USE",          # Email đã đăng ký rồi
                        "Email đã được sử dụng",         # Thông báo tiếng Việt
                        "KeyboardInterrupt",             # User tự tắt
                        "REGION_BLOCKED",                # Account bị chặn vùng/quốc gia
                        "WRONG_PASSWORD",                # Sai mật khẩu BNID
                        "BNID_LOGIN_ERROR",              # Lỗi login BNID khác
                    ]
                    is_permanent = any(kw in error_msg for kw in NO_RETRY_KEYWORDS)
                    
                    if is_permanent:
                        log.error(f"🚫 Lỗi KHÔNG THỂ RETRY: {error_msg[:200]}")
                        if "EMAIL_ALREADY_IN_USE" in error_msg or "Email đã được sử dụng" in error_msg:
                            result_data["status"] = "HAS_BNID"
                            result_data["error_details"] = "Email đã được sử dụng, chuyển HAS_BNID để thử login ở lượt sau."
                            log.warning("🔄 " + result_data["error_details"])
                        else:
                            result_data["status"] = "FAIL_NO_RETRY"
                            result_data["error_details"] = error_msg[:200]
                        if proxy_idx >= 0:
                            self.proxy_pool.mark_used(proxy_idx)
                        break  # Thoát vòng retry ngay
                    
                    # ─── Lỗi CÓ THỂ RETRY ───
                    # Đánh dấu proxy chết nếu lỗi mạng
                    is_proxy_error = False
                    if "net::ERR_" in error_msg or "Target page, context or browser has been closed" in error_msg or "Timeout" in error_msg:
                        if config.USE_PROXY:
                            log.warning(f"   -> Lỗi mạng/trình duyệt, đánh dấu proxy chết...")
                        else:
                            log.warning(f"   -> Lỗi mạng/trình duyệt (Kết nối trực tiếp/Không dùng proxy)...")
                        if proxy_idx >= 0:
                            self.proxy_pool.mark_failed(proxy_idx)
                        is_proxy_error = True
                    
                    if result_data["bnid_user_code"] != "":
                        log.info("   -> Đã tạo BNID thành công nhưng lỗi ở bước sau. Đánh dấu HAS_BNID và bỏ qua không thử lại.")
                        result_data["status"] = "HAS_BNID"
                        if proxy_idx >= 0:
                            self.proxy_pool.mark_used(proxy_idx)
                        break

                    result_data["status"] = "FAILED"
                    result_data["error_details"] = error_msg[:200]
                        
                    if attempt == max_retries:
                        log.error(f"❌ Đã thử {max_retries} lần đều thất bại cho {email}")
                        if not is_proxy_error:
                            if proxy_idx >= 0:
                                self.proxy_pool.mark_used(proxy_idx)
                        break
                    else:
                        # MỞ KHÓA proxy trước khi retry để worker khác có thể dùng
                        if proxy_idx >= 0:
                            self.proxy_pool.release_proxy(proxy_idx)
                        log.info("⏳ Lỗi có thể retry. Thử lại sau 2 giây...")
                        import time
                        # Chờ ngắt quãng để phản hồi STOP ngay lập tức
                        for _ in range(4):
                            if config.STOP_FLAG: break
                            time.sleep(0.5)

            # MỞ KHÓA proxy sau khi xử lý xong account (dù thành công hay thất bại)
            if proxy_idx >= 0:
                self.proxy_pool.release_proxy(proxy_idx)

            # Kết quả cuối cùng — luôn ghi vào Accounts (upsert)
            self.sheets_manager.update_email_status(raw_email, result_data["status"], result_data.get("error_details", ""))
            self.sheets_manager.append_account(result_data)
            self._finish_task(result_data["status"])
            log.info(f"Kết thúc xử lý tài khoản {email}\n" + "-"*50)

            if config.STOP_FLAG:
                log.warning("🛑 Nhận lệnh STOP hoặc kịch bản dừng (như quá tải), kết thúc luồng.")
                break
                
            # Đợi 45 giây độc lập cho mỗi worker trước khi làm account tiếp theo
            if not self.email_queue.empty():
                log.info("⏳ Tạm nghỉ 45 giây trước khi bốc account tiếp theo...")
                import time
                for _ in range(90):
                    if config.STOP_FLAG:
                        break
                    time.sleep(0.5)

    async def _process_account_async(self, email, password, nickname, birthday, prefecture, proxy, result_data, has_bnid_local, email_password: str = "", refresh_token: str = "", client_id: str = "", otp_email: str = "", otp_pass: str = "", provider: str = ""):
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
                    client_id=client_id,
                    otp_email=otp_email,
                    otp_pass=otp_pass,
                    provider=provider
                )
                result_data["bnid_user_code"] = "TRUE"
                log.info(f"✅ Step 3 done — Đã qua bước OTP Email, đặt BNID = TRUE")
                # Ghi ngay vào Accounts sau khi OTP email thành công
                self.sheets_manager.append_account(result_data)
            except Exception as e:
                err = str(e)
                if "IP_BANNED" in err:
                    raise e
                if "REGION_BLOCKED" in err:
                    raise Exception(f"REGION_BLOCKED: {err}")
                if "WRONG_PASSWORD" in err:
                    raise Exception(f"WRONG_PASSWORD: {err}")
                if "BNID_LOGIN_ERROR" in err:
                    raise Exception(f"BNID_LOGIN_ERROR: {err}")
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
                        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
                        # BNID thường có dạng B + 12 số (vd: B999888777666) hoặc 12 số nằm gần chữ BNID hoặc ユーザーコード
                        m = _re.search(r'(?:BNID|ユーザーコード|ID)[\s:：]*([B]\d{12}|\d{12})\b', text, _re.IGNORECASE)
                        if not m:
                            m = _re.search(r'\b(B\d{12})\b', text)
                        if m:
                            bnid = m.group(1).strip()
                            log.info(f"🔍 [{url}] Tìm thấy chuỗi nghi ngờ BNID: {bnid}")
                            return bnid
                        else:
                            text_preview = text[:300]
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
                            if "アクセス集中" in body_text or "エラーが発生しました" in body_text or "A system error has occurred" in body_text:
                                is_overloaded = True
                        except:
                            pass

                        if not config.STOP_FLAG:
                            screenshot_path = str(config.DATA_DIR / f"error_fatal_{email.replace('+', '_')}.png")
                            await page.screenshot(path=screenshot_path, timeout=5000)
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
