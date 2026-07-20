import time
import re
import asyncio
import datetime
import requests
from src.utils.logger import get_logger

log = get_logger("email_reader_dongvanfb")

# ═══════════════════════════════════════════════════════════════
# Microsoft Graph API — đọc email trực tiếp, không qua DongVanFB
# ═══════════════════════════════════════════════════════════════

def _get_access_token(refresh_token: str, client_id: str) -> str | None:
    """Đổi refresh_token lấy access_token từ Microsoft."""
    url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "https://graph.microsoft.com/Mail.Read offline_access"
    }
    try:
        r = requests.post(url, data=data, timeout=15)
        if r.status_code == 200:
            return r.json().get("access_token")
        else:
            log.warning(f"MS Token error {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        log.warning(f"MS Token request failed: {e}")
        return None


def _read_inbox_graph(access_token: str, top: int = 10) -> list[dict]:
    """Đọc inbox qua Microsoft Graph API, trả về list messages."""
    url = (
        "https://graph.microsoft.com/v1.0/me/messages"
        f"?$top={top}&$orderby=receivedDateTime desc"
        "&$select=subject,from,receivedDateTime,body"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json().get("value", [])
        else:
            log.warning(f"Graph API error {r.status_code}: {r.text[:200]}")
            return []
    except Exception as e:
        log.warning(f"Graph API request failed: {e}")
        return []


def _extract_otp_from_graph_message(msg: dict, since_ts: float | None) -> str | None:
    """Trích OTP từ message Graph API. Trả về OTP string hoặc None."""
    from_addr = msg.get("from", {}).get("emailAddress", {}).get("address", "").lower()
    subject = msg.get("subject", "")
    body_content = msg.get("body", {}).get("content", "")
    received_dt = msg.get("receivedDateTime", "")

    # Chỉ xét email từ Bandai
    if "bandai" not in from_addr and "banapassport" not in from_addr and "bandai" not in subject.lower():
        return None

    # Filter theo thời gian (bỏ email cũ hơn since_ts - 600s)
    if since_ts and received_dt:
        try:
            dt = datetime.datetime.fromisoformat(received_dt.replace("Z", "+00:00"))
            msg_ts = dt.timestamp()
            if msg_ts < since_ts - 600:
                return None
        except Exception:
            pass

    log.info(f"  📧 Email Bandai! from={from_addr} | subj={subject[:60]} | date={received_dt}")

    # Parse OTP từ body HTML
    match = re.search(r'authcode=(\d{6})', body_content)
    if not match:
        match = re.search(r'Authorization Code[^\d]*(\d{6})', body_content, re.IGNORECASE)
    if not match:
        match = re.search(r'認証コード[^\d]*(\d{6})', body_content, re.IGNORECASE)
    if not match:
        match = re.search(r'\b(\d{6})\b', body_content)

    if match:
        return match.group(1)

    log.warning(f"  ⚠️ Email Bandai nhưng không parse được OTP! Body length={len(body_content)}")
    return None


# ═══════════════════════════════════════════════════════════════
# DongVanFB Fallback — dùng khi Graph API không khả dụng
# ═══════════════════════════════════════════════════════════════

def _poll_dongvanfb(email: str, refresh_token: str, client_id: str, since_ts: float | None) -> str | None:
    """Gọi DongVanFB API 1 lần, trả OTP hoặc None."""
    url = "https://tools.dongvanfb.net/api/get_messages_oauth2"
    payload = {
        "email": email,
        "refresh_token": refresh_token,
        "client_id": client_id
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
    except Exception as e:
        log.debug(f"DongVanFB request failed: {e}")
        return None

    if resp.status_code != 200:
        log.debug(f"DongVanFB HTTP {resp.status_code}")
        return None

    resp_json = resp.json()
    messages = []
    if isinstance(resp_json, dict):
        if "data" in resp_json and isinstance(resp_json["data"], list):
            messages = resp_json["data"]
        elif "messages" in resp_json and isinstance(resp_json["messages"], list):
            messages = resp_json["messages"]
    elif isinstance(resp_json, list):
        messages = resp_json

    # Kiểm tra response chỉ là health-check (không có messages)
    if not messages and isinstance(resp_json, dict) and resp_json.get("message") == "API is working":
        return None

    for msg in reversed(messages):
        from_addr = str(msg.get("from", "")).lower()
        subject = str(msg.get("subject", ""))
        message_body = str(msg.get("message", ""))
        api_code = str(msg.get("code", "")).strip()

        if "bandai" not in from_addr and "banapassport" not in from_addr and "bandai" not in subject.lower():
            continue

        if api_code and api_code.isdigit() and len(api_code) == 6:
            return api_code

        match = re.search(r'authcode=(\d{6})', message_body)
        if not match:
            match = re.search(r'Authorization Code[^\d]*(\d{6})', message_body, re.IGNORECASE)
        if not match:
            match = re.search(r'認証コード[^\d]*(\d{6})', message_body, re.IGNORECASE)
        if not match:
            match = re.search(r'\b(\d{6})\b', message_body)
        if match:
            return match.group(1)

    return None


# ═══════════════════════════════════════════════════════════════
# Entry point — ưu tiên Graph API, fallback DongVanFB
# ═══════════════════════════════════════════════════════════════

async def get_bandai_namco_otp_dongvanfb(
    email: str,
    refresh_token: str,
    client_id: str,
    timeout: int = 120,
    poll_interval: int = 5,
    since_ts: float | None = None
) -> str | None:
    """
    Đọc OTP email Bandai Namco.
    Ưu tiên: Microsoft Graph API trực tiếp (nhanh, ổn định).
    Fallback: DongVanFB tools API (khi Graph API thất bại).
    """
    log.info(f"Email Reader: Bắt đầu poll OTP cho {email}...")
    start_ts = time.time()

    # ── Thử lấy access_token từ Microsoft ──
    access_token = await asyncio.to_thread(_get_access_token, refresh_token, client_id)
    use_graph = access_token is not None
    if use_graph:
        log.info("📡 Sử dụng Microsoft Graph API trực tiếp để đọc email.")
    else:
        log.warning("⚠️ Không lấy được MS access_token. Fallback sang DongVanFB API.")

    while time.time() - start_ts < timeout:
        try:
            otp = None
            if use_graph:
                # Graph API: đọc 10 email mới nhất
                messages = await asyncio.to_thread(_read_inbox_graph, access_token, 10)
                if messages:
                    log.info(f"📬 Graph API: {len(messages)} email, đang quét OTP...")
                    for msg in messages:
                        otp = _extract_otp_from_graph_message(msg, since_ts)
                        if otp:
                            break
                else:
                    log.info("⏳ Graph API: Chưa có thư mới, đang chờ...")
            else:
                # DongVanFB fallback
                otp = await asyncio.to_thread(
                    _poll_dongvanfb, email, refresh_token, client_id, since_ts
                )
                if not otp:
                    log.info("⏳ DongVanFB API: Chưa có thư mới, đang chờ...")

            if otp:
                log.info(f"✅ Đã lấy OTP: {otp}")
                return otp

        except Exception as e:
            elapsed = int(time.time() - start_ts)
            log.warning(f"Email reader error ({elapsed}s/{timeout}s): {e}")

        await asyncio.sleep(poll_interval)

    log.error("Email Reader: Hết thời gian chờ OTP.")
    return None
