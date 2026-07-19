import requests
import time
import re
from src.utils.logger import get_logger

log = get_logger("email_reader_dongvanfb")

async def get_bandai_namco_otp_dongvanfb(
    email: str,
    refresh_token: str,
    client_id: str,
    timeout: int = 120,
    poll_interval: int = 5,
    since_ts: float | None = None
) -> str | None:
    """
    Sử dụng API của DongVanFB để đọc OTP.
    - Dùng endpoint get_messages_oauth2 để có danh sách tin nhắn,
    hoặc dùng graph_code để xem nó có lấy được code thẳng không.
    """
    log.info(f"DongVanFB API: Bắt đầu poll OTP cho {email}...")
    
    url = "https://tools.dongvanfb.net/api/get_messages_oauth2"
    payload = {
        "email": email,
        "refresh_token": refresh_token,
        "client_id": client_id
    }
    
    start_ts = time.time()
    api_error_count = 0
    
    import requests
    import asyncio
    
    while time.time() - start_ts < timeout:
        try:
            # Chạy requests trong một thread riêng để không block event loop
            resp = await asyncio.to_thread(
                requests.post,
                url,
                json=payload,
                timeout=15
            )
            
            if resp.status_code == 200:
                resp_json = resp.json()
                
                messages = []
                if isinstance(resp_json, dict):
                    if "data" in resp_json and isinstance(resp_json["data"], list):
                        messages = resp_json["data"]
                    elif "messages" in resp_json and isinstance(resp_json["messages"], list):
                        messages = resp_json["messages"]
                elif isinstance(resp_json, list):
                    messages = resp_json
                    
                if isinstance(resp_json, dict) and "status" in resp_json and str(resp_json["status"]).lower() in ["error", "false"]:
                    api_error_count += 1
                    if api_error_count >= 2:
                        log.error(f"❌ DongVanFB API từ chối token liên tục (Lỗi: {resp_json}). Huỷ lấy OTP ngay lập tức!")
                        return None
                    else:
                        log.warning(f"⚠️ DongVanFB API từ chối token (Lỗi: {resp_json}). Đang thử lại lần {api_error_count}...")
                        messages = []
                
                if len(messages) == 0:
                    log.info(f"⏳ DongVanFB API: Chưa có thư mới, đang chờ...")
                else:
                    log.info(f"⏳ DongVanFB API: Tìm thấy {len(messages)} tin nhắn, đang quét OTP...")
                    
                for msg in messages:
                    from_addr = str(msg.get("from", "")).lower()
                    subject = str(msg.get("subject", ""))
                    message_body = str(msg.get("message", ""))
                    msg_date_str = str(msg.get("date", ""))
                    api_code = str(msg.get("code", "")).strip()  # Field code API tự parse sẵn

                    log.debug(f"  📨 [{msg_date_str}] from={from_addr} | subject={subject[:50]} | api_code={api_code!r}")

                    if since_ts and msg_date_str:
                        try:
                            import datetime
                            # format: HH:MM - DD/MM/YYYY — API trả về giờ Việt Nam (UTC+7)
                            dt = datetime.datetime.strptime(msg_date_str, "%H:%M - %d/%m/%Y")
                            # Coi như UTC+7, convert sang UTC timestamp để so sánh với since_ts (UTC)
                            msg_ts = dt.timestamp() - (7 * 3600)
                            if msg_ts < since_ts - 600:  # Cho phép chênh lệch 10 phút
                                log.debug(f"  ⏩ Bỏ qua email cũ: msg_ts={msg_ts:.0f} < since_ts-600={since_ts-600:.0f}")
                                continue
                        except Exception:
                            pass
                            
                    if "bandai" in from_addr or "banapassport" in from_addr or "bandai" in subject.lower():
                        log.info(f"  📧 Email Bandai tìm thấy! from={from_addr} | subject={subject[:60]}")

                        # Ưu tiên dùng field `code` mà API đã parse sẵn
                        if api_code and api_code.isdigit() and len(api_code) == 6:
                            log.info(f"✅ Lấy OTP từ field `code` của DongVanFB API: {api_code}")
                            return api_code

                        # Tự parse từ body HTML nếu API chưa extract
                        match = re.search(r'authcode=(\d{6})', message_body)
                        if not match:
                            match = re.search(r'Authorization Code[^\d]*(\d{6})', message_body, re.IGNORECASE)
                        if not match:
                            match = re.search(r'認証コード[^\d]*(\d{6})', message_body, re.IGNORECASE)
                        if not match:
                            match = re.search(r'\b(\d{6})\b', message_body)

                        if match:
                            code = match.group(1)
                            log.info(f"✅ Đã parse OTP từ body DongVanFB: {code}")
                            return code
                        else:
                            log.warning(f"  ⚠️ Email Bandai tìm thấy nhưng không parse được OTP! Body length={len(message_body)}")
            else:
                api_error_count += 1
                if api_error_count >= 2:
                    log.error(f"❌ DongVanFB API trả về mã lỗi HTTP {resp.status_code}: {resp.text}. Huỷ lấy OTP ngay lập tức!")
                    return None
                else:
                    log.warning(f"⚠️ DongVanFB API trả về mã lỗi HTTP {resp.status_code}. Đang thử lại lần {api_error_count}...")

        except Exception as e:
            log.warning(f"DongVanFB API error: {e}")
            
        await asyncio.sleep(poll_interval)

    log.error("DongVanFB API: Hết thời gian chờ OTP.")
    return None
