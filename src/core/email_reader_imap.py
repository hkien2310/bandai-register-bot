"""
email_reader_imap.py - Module lấy mã OTP của Bandai Namco từ Email thông qua giao thức IMAP (dùng App Password)
"""
import imaplib
import email
from email.header import decode_header
import re
import time
from datetime import datetime, timezone
import dateutil.parser

from src.utils.logger import get_logger

log = get_logger("email_reader_imap")

import threading

# Quản lý giới hạn kết nối song song toàn cục cho từng nhà cung cấp mail
# iCloud: tối đa 3 kết nối IMAP đồng thời
# Gmail: tối đa 5 kết nối IMAP đồng thời
_IMAP_SEMAPHORES = {
    "imap.mail.me.com": threading.Semaphore(3),
    "imap.gmail.com": threading.Semaphore(2),
}
_DEFAULT_SEMAPHORE = threading.Semaphore(3)

def _get_imap_server(email_address: str) -> str:
    """Trả về IMAP server tương ứng với đuôi email."""
    domain = email_address.split("@")[-1].lower()
    if domain in ["gmail.com"]:
        return "imap.gmail.com"
    elif domain in ["icloud.com", "me.com", "mac.com"]:
        return "imap.mail.me.com"
    else:
        # Mặc định thử gmail nếu không rõ
        return "imap.gmail.com"

class IMAPSessionManager:
    """
    Quản lý kết nối IMAP tập trung dùng chung cho nhiều Worker.
    - Tất cả worker cùng đăng ký qua hòm otp_email sẽ TÁI SỬ DỤNG DUY NHẤT 1 KẾT NỐI IMAP.
    - Đếm số worker đang sử dụng kết nối (ref_count).
    - CHỈ ĐĂNG XUẤT (mail.logout()) VÀ GIẢI PHÓNG KẾT NỐI KHI TẤT CẢ WORKER ĐỀU ĐÃ XONG (ref_count = 0).
    """
    def __init__(self):
        self._sessions = {}
        self._manager_lock = threading.Lock()

    def acquire_session(self, otp_email: str):
        with self._manager_lock:
            if otp_email not in self._sessions:
                self._sessions[otp_email] = {
                    "mail": None,
                    "ref_count": 0,
                    "lock": threading.Lock()
                }
            sess = self._sessions[otp_email]
            sess["ref_count"] += 1
            return sess

    def release_session(self, otp_email: str):
        with self._manager_lock:
            sess = self._sessions.get(otp_email)
            if sess:
                sess["ref_count"] = max(0, sess["ref_count"] - 1)
                if sess["ref_count"] == 0:
                    mail = sess.get("mail")
                    if mail:
                        try:
                            mail.logout()
                            log.info(f"[{otp_email}] 🚪 Tất cả worker đã hoàn tất. Đóng kết nối IMAP tập trung.")
                        except Exception:
                            pass
                        sess["mail"] = None
                    del self._sessions[otp_email]

_SESSION_MANAGER = IMAPSessionManager()

def get_bandai_namco_otp_imap(
    target_email: str,
    otp_email: str,
    otp_pass: str,
    timeout: int = 120,
    since_ts: float = 0
) -> str:
    """
    Kết nối vào hộp thư `otp_email` bằng IMAP và mật khẩu ứng dụng `otp_pass`.
    Quét hộp thư INBOX để tìm email gửi từ noreply@id.banapassport.net.
    Lọc các email có nội dung đề cập tới `target_email` (nếu dùng alias).
    Trả về chuỗi 6 số hoặc chuỗi rỗng nếu thất bại/hết giờ.
    """
    if not otp_email or not otp_pass:
        log.error(f"[{target_email}] Thiếu otp_email hoặc otp_pass để đăng nhập IMAP.")
        return ""

    imap_server = _get_imap_server(otp_email)
    sem = _IMAP_SEMAPHORES.get(imap_server, _DEFAULT_SEMAPHORE)
    log.info(f"[{target_email}] Đang chờ OTP từ {otp_email} qua {imap_server} (Timeout: {timeout}s)")
    
    import src.config as config
    start_time = time.time()
    poll_count = 0
    
    session = _SESSION_MANAGER.acquire_session(otp_email)
    
    try:
        while time.time() - start_time < timeout:
            if getattr(config, "STOP_FLAG", False):
                log.warning(f"[{target_email}] 🛑 Nhận lệnh STOP, dừng tiến trình đọc IMAP.")
                return ""

            try:
                with session["lock"]:
                    mail = session["mail"]
                    # 1. Đăng nhập IMAP tập trung duy nhất 1 lần nếu chưa có
                    if mail is None:
                        log.info(f"[{target_email}] ⏳ Kết nối & Đăng nhập IMAP tập trung ({imap_server})...")
                        with sem:
                            log.info(f"[{target_email}] 🔗 Vào IMAP slot — đăng nhập {otp_email}...")
                            mail = imaplib.IMAP4_SSL(imap_server, timeout=30)
                            mail.login(otp_email, otp_pass)
                            mail.select("inbox")
                            session["mail"] = mail
                    else:
                        try:
                            # Kiểm tra xem kết nối IMAP dùng chung có còn sống hay không
                            status, _ = mail.noop()
                            if status != "OK":
                                session["mail"] = None
                                mail = None
                                continue
                        except Exception:
                            session["mail"] = None
                            mail = None
                            continue

                    # 2. Tìm kiếm email Bandai Namco trên kết nối IMAP tập trung
                    since_date = time.strftime("%d-%b-%Y", time.gmtime(since_ts if since_ts > 0 else time.time() - 600))
                    status, messages = mail.search(None, f'(FROM "noreply@id.banapassport.net" SINCE {since_date})')

                    if status == "OK" and messages[0]:
                        msg_nums = messages[0].split()
                        top_nums = msg_nums[-5:]
                        
                        num_str = b','.join(top_nums).decode()
                        res, fetch_data = mail.fetch(num_str, "(BODY.PEEK[])")
                        
                        if res == "OK" and fetch_data:
                            for item in reversed(fetch_data):
                                if not isinstance(item, tuple) or not item[1]:
                                    continue
                                raw_email = item[1]
                                msg = email.message_from_bytes(raw_email)

                                # 1. Kiểm tra timestamp
                                date_tuple = email.utils.parsedate_tz(msg['Date'])
                                if date_tuple:
                                    mail_ts = float(email.utils.mktime_tz(date_tuple))
                                    if since_ts > 0 and mail_ts < (since_ts - 10):
                                        continue

                                # 2. Kiểm tra TO address / Target email
                                to_address = str(msg.get("To", "")).lower()
                                
                                body = ""
                                if msg.is_multipart():
                                    for part in msg.walk():
                                        if part.get_content_type() == "text/plain":
                                            try:
                                                charset = part.get_content_charset() or 'utf-8'
                                                body = part.get_payload(decode=True).decode(charset, errors='replace')
                                            except:
                                                pass
                                else:
                                    try:
                                        charset = msg.get_content_charset() or 'utf-8'
                                        body = msg.get_payload(decode=True).decode(charset, errors='replace')
                                    except:
                                        pass

                                if body and (target_email in to_address or target_email in body.lower()):
                                    match = re.search(r'\b([0-9]{6})\b', body)
                                    if match:
                                        otp_code = match.group(1)
                                        log.info(f"[{target_email}] ✅ Đã tìm thấy mã OTP: {otp_code}")
                                        return otp_code
            except imaplib.IMAP4.error as auth_err:
                session["mail"] = None
                err_str = str(auth_err)
                if "Too many simultaneous connections" in err_str or "simultaneous connections" in err_str.lower():
                    log.warning(f"⚠️ [{target_email}] Máy chủ IMAP giới hạn kết nối song song. Đang đợi 3s để thử lại...")
                    time.sleep(3)
                    continue
                elif "AUTHENTICATIONFAILED" in err_str or "Invalid credentials" in err_str or "LOGIN failed" in err_str:
                    domain = str(otp_email).split("@")[-1].lower() if "@" in str(otp_email) else ""
                    if "icloud.com" in domain or "me.com" in domain or "mac.com" in domain:
                        log.error(
                            f"❌ [{target_email}] Lỗi đăng nhập IMAP iCloud ({otp_email}): Sai mật khẩu hoặc chưa tạo Mật khẩu dành cho ứng dụng (App-Specific Password)!\n"
                            f"👉 HƯỚNG DẪN KHẮC PHỤC DÀNH CHO iCLOUD MAIL:\n"
                            f"   1. Truy cập tài khoản Apple ID '{otp_email}' tại: https://appleid.apple.com\n"
                            f"   2. Vào mục 'Sign-In and Security' (Đăng nhập và Bảo mật) ➔ Chọn 'App-Specific Passwords' (Mật khẩu dành cho ứng dụng).\n"
                            f"   3. Tạo mật khẩu ứng dụng mới (dạng xxxx-xxxx-xxxx-xxxx).\n"
                            f"   4. Điền mật khẩu 16 ký tự này vào file XLSX (cột otp_pass hoặc email_password) thay cho mật khẩu iCloud thông thường."
                        )
                    elif "gmail.com" in domain or "googlemail.com" in domain:
                        log.error(
                            f"❌ [{target_email}] Lỗi đăng nhập IMAP Gmail ({otp_email}): Sai mật khẩu hoặc chưa tạo Mật khẩu ứng dụng (App Password)!\n"
                            f"👉 HƯỚNG DẪN KHẮC PHỤC DÀNH CHO GMAIL:\n"
                            f"   1. Truy cập tài khoản Google '{otp_email}' và bật 'Xác minh 2 bước' (2-Step Verification).\n"
                            f"   2. Vào đường dẫn: https://myaccount.google.com/apppasswords để tạo 'Mật khẩu ứng dụng' (16 ký tự).\n"
                            f"   3. Điền mật khẩu 16 ký tự này vào file XLSX (cột otp_pass hoặc email_password) thay cho mật khẩu Gmail thông thường."
                        )
                    else:
                        log.error(
                            f"❌ [{target_email}] Lỗi đăng nhập IMAP ({otp_email}): Mật khẩu hoặc tài khoản IMAP không chính xác! Vui lòng kiểm tra lại cột otp_email và otp_pass trong file XLSX."
                        )
                    return ""

                else:
                    log.error(f"[{target_email}] Lỗi IMAP Auth: {auth_err}")
            except (OSError, TimeoutError, ConnectionError) as net_err:
                session["mail"] = None
                log.warning(f"⚠️ [{target_email}] Lỗi mạng khi kết nối IMAP ({imap_server}): {net_err}. Thử lại sau 5s...")
            except Exception as e:
                session["mail"] = None
                log.warning(f"⚠️ [{target_email}] Lỗi kết nối IMAP không xác định: {type(e).__name__}: {e}. Thử lại sau 5s...")
                
            poll_count += 1
            elapsed = int(time.time() - start_time)
            if poll_count % 2 == 0:
                log.info(f"⏳ [{target_email}] Đang chờ Bandai Namco gửi mã OTP về hòm thư (Đã chờ {elapsed}s/{timeout}s)...")
            for _ in range(10):
                if getattr(config, "STOP_FLAG", False):
                    log.warning(f"[{target_email}] 🛑 Nhận lệnh STOP, dừng tiến trình đọc IMAP.")
                    return ""
                time.sleep(0.5)
            
        log.warning(f"[{target_email}] Hết thời gian ({timeout}s) không nhận được OTP qua IMAP.")
        return ""
    finally:
        _SESSION_MANAGER.release_session(otp_email)


def get_gmail_dot_alias(base_email: str, index: int) -> str:
    username, domain = base_email.split("@", 1)
    if domain.lower() not in ["gmail.com", "googlemail.com"]:
        return base_email
    
    gaps = len(username) - 1
    if gaps <= 0:
        return base_email
        
    binary_str = bin(index % (2 ** gaps))[2:].zfill(gaps)
    result = []
    for i, char in enumerate(username):
        result.append(char)
        if i < gaps and binary_str[i] == '1':
            result.append('.')
    return "".join(result) + "@" + domain

def generate_account_email(account_id: int | str) -> str:
    import src.config as config
    prefix = getattr(config, "CATCHALL_EMAIL_PREFIX", "acc")
    suffix = f"{account_id:05d}" if isinstance(account_id, int) else str(account_id)

    if getattr(config, "EMAIL_MODE", "alias") == "alias":
        catchall_inbox = getattr(config, "CATCHALL_INBOX", None)
        if not catchall_inbox:
            raise ValueError("CATCHALL_INBOX not configured in .env")
        base, domain = catchall_inbox.split("@", 1)
        if domain.lower() in ["gmail.com", "googlemail.com"]:
            try:
                idx = int(suffix)
            except ValueError:
                idx = abs(hash(suffix))
            return get_gmail_dot_alias(catchall_inbox, idx)
        else:
            return f"{base}+{prefix}{suffix}@{domain}"
    else:
        catchall_domain = getattr(config, "CATCHALL_DOMAIN", None)
        if not catchall_domain:
            raise ValueError("CATCHALL_DOMAIN not configured in .env")
        return f"{prefix}{suffix}@{catchall_domain}"
