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
    Dùng API DongVanFB để đọc OTP email Bandai Namco.
    Poll liên tục cho đến khi hết timeout hoặc tìm được OTP.
    Chỉ thoát sớm khi token bị từ chối (401/403) hoặc API báo lỗi token liên tục.
    Lỗi 502/503 (server chập chờn) sẽ KHÔNG thoát sớm, tiếp tục chờ.
    """
    log.info(f"DongVanFB API: Bắt đầu poll OTP cho {email}...")

    url = "https://tools.dongvanfb.net/api/get_messages_oauth2"
    payload = {
        "email": email,
        "refresh_token": refresh_token,
        "client_id": client_id
    }

    start_ts = time.time()
    token_error_count = 0  # Chỉ đếm lỗi token thực sự, không đếm 502

    import asyncio

    while time.time() - start_ts < timeout:
        try:
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

                # Thoát sớm chỉ khi token bị từ chối liên tục (không phải lỗi server 5xx)
                if isinstance(resp_json, dict) and "status" in resp_json and str(resp_json["status"]).lower() in ["error", "false"]:
                    token_error_count += 1
                    if token_error_count >= 3:
                        log.error(f"❌ DongVanFB API từ chối token liên tục {token_error_count} lần ({resp_json}). Huỷ lấy OTP!")
                        return None
                    log.warning(f"⚠️ DongVanFB API từ chối token lần {token_error_count}: {resp_json}. Tiếp tục thử...")
                    messages = []
                else:
                    token_error_count = 0  # Reset khi response hợp lệ

                if len(messages) == 0:
                    log.info("⏳ DongVanFB API: Chưa có thư mới, đang chờ...")
                else:
                    log.info(f"⏳ DongVanFB API: Tìm thấy {len(messages)} tin nhắn, đang quét OTP...")

                for msg in messages:
                    from_addr = str(msg.get("from", "")).lower()
                    subject = str(msg.get("subject", ""))
                    message_body = str(msg.get("message", ""))
                    msg_date_str = str(msg.get("date", ""))
                    api_code = str(msg.get("code", "")).strip()

                    log.debug(f"  📨 [{msg_date_str}] from={from_addr} | subject={subject[:50]} | api_code={api_code!r}")

                    if since_ts and msg_date_str:
                        try:
                            import datetime
                            # DongVanFB luôn trả giờ Việt Nam (UTC+7) — parse tường minh
                            vn_tz = datetime.timezone(datetime.timedelta(hours=7))
                            dt = datetime.datetime.strptime(msg_date_str, "%H:%M - %d/%m/%Y")
                            dt_aware = dt.replace(tzinfo=vn_tz)
                            msg_ts = dt_aware.timestamp()
                            if msg_ts < since_ts - 600:
                                log.debug(f"  ⏩ Bỏ qua email cũ: {msg_date_str}")
                                continue
                        except Exception:
                            pass

                    if "bandai" in from_addr or "banapassport" in from_addr or "bandai" in subject.lower():
                        log.info(f"  📧 Email Bandai tìm thấy! from={from_addr} | subject={subject[:60]}")

                        # Ưu tiên field `code` API đã parse sẵn
                        if api_code and api_code.isdigit() and len(api_code) == 6:
                            log.info(f"✅ Lấy OTP từ field `code` của DongVanFB API: {api_code}")
                            return api_code

                        # Tự parse từ body HTML
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

            elif resp.status_code in (401, 403):
                # Token không hợp lệ → thoát ngay
                log.error(f"❌ DongVanFB API lỗi xác thực HTTP {resp.status_code}. Token không hợp lệ, huỷ OTP!")
                return None
            else:
                # 502/503/504 hoặc lỗi server khác → KHÔNG thoát, tiếp tục poll hết timeout
                elapsed = int(time.time() - start_ts)
                log.warning(f"⚠️ DongVanFB server lỗi HTTP {resp.status_code} ({elapsed}s/{timeout}s). Tiếp tục chờ...")

        except Exception as e:
            elapsed = int(time.time() - start_ts)
            log.warning(f"DongVanFB API error ({elapsed}s/{timeout}s): {e}")

        await asyncio.sleep(poll_interval)

    log.error("DongVanFB API: Hết thời gian chờ OTP.")
    return None
