import threading
import time
import requests
import json
from pathlib import Path

import src.config as config
from src.utils.logger import get_logger

log = get_logger("sms_service")

_BASE = config.SMS_BASE_URL.rstrip("/")
_apikey: str = ""
_apikey_expires: float = 0.0
_apikey_lock = threading.Lock()

def _get_apikey() -> str:
    """Get apikey from cache or API. Thread-safe."""
    global _apikey, _apikey_expires
    
    # Nếu đã cấu hình cứng sms_api_key trong config.json, dùng luôn không cần gọi API getKey
    if config.SMS_API_KEY:
        return config.SMS_API_KEY
        
    with _apikey_lock:
        now = time.time()
        
        # 1. Memory cache check
        if _apikey and now < _apikey_expires - 300:
            return _apikey

        # 2. Disk cache check
        cache_path = config.DATA_DIR / "sms_apikey.json"
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                file_key = cache_data.get("apikey")
                file_expires = cache_data.get("expires_at", 0.0)
                
                if file_key and now < file_expires - 300:
                    _apikey = file_key
                    _apikey_expires = file_expires
                    return _apikey
            except Exception as e:
                log.warning(f"Không đọc được file cache apikey: {e}")

        # 3. Request new apikey
        if not config.SMS_USERNAME or not config.SMS_PASSWORD:
            raise RuntimeError("SMS_USERNAME / SMS_PASSWORD chưa cấu hình trong .env")

        log.info("Lấy SMS apikey mới từ API...")
        resp = requests.post(
            f"{_BASE}/api/ext/getKey",
            json={"username": config.SMS_USERNAME, "password": config.SMS_PASSWORD},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "success":
            raise RuntimeError(f"getKey thất bại: {data}")

        _apikey = data["apikey"]
        _apikey_expires = data["expires_at"] / 1000
        
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"apikey": _apikey, "expires_at": _apikey_expires}, f)
            log.info("Đã lưu SMS apikey mới vào file cache.")
        except Exception as e:
            log.warning(f"Không ghi được file cache apikey: {e}")

        log.info(f"✅ Apikey OK (expires at: {time.strftime('%H:%M:%S', time.localtime(_apikey_expires))})")
        return _apikey

def check_balance() -> int:
    """Check SMS API balance."""
    try:
        apikey = _get_apikey()
        resp = requests.get(
            f"{_BASE}/api/ext/balance",
            params={"apikey": apikey},
            timeout=10,
        )
        data = resp.json()
        if data.get("status") == "success":
            balance = data["balance"]
            log.info(f"💰 Số dư SMS: {balance:,} điểm/yên")
            return balance
    except Exception as e:
        log.warning(f"Không lấy được số dư: {e}")
    return -1

def order_phone(
    country: str | None = None,
    service_id: str | None = None,
    server: str | None = None,
) -> dict:
    """
    Order phone number. Poll until phone number is ready.
    """
    apikey = _get_apikey()
    params = {
        "apikey":    apikey,
        "serviceId": service_id or config.SMS_SERVICE_ID,
        "server":    server     or config.SMS_SERVER,
        "country":   country    or config.SMS_COUNTRY,
    }
    log.info(f"📱 Order phone | country={params['country']} serviceId={params['serviceId']}")

    resp = requests.get(f"{_BASE}/api/ext/order", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "success":
        raise RuntimeError(f"order thất bại: {data.get('message', data)}")

    pkey = data["pkey"]
    phone = data.get("phone", "").strip()

    # If phone is not ready, poll getSms to retrieve the actual number
    if not phone or "xin số" in phone or not any(c.isdigit() for c in phone):
        log.info("📱 Số điện thoại chưa sẵn sàng, đang poll getSms để lấy số thực tế...")
        max_attempts = 12
        for attempt in range(1, max_attempts + 1):
            time.sleep(1.5)
            try:
                get_resp = requests.get(
                    f"{_BASE}/api/ext/getSms",
                    params={"apikey": apikey, "pkey": pkey},
                    timeout=10,
                )
                get_data = get_resp.json()
                curr_phone = get_data.get("phone", "").strip()
                if curr_phone and "xin số" not in curr_phone and any(c.isdigit() for c in curr_phone):
                    phone = curr_phone
                    log.info(f"  [SUCCESS] Lấy số thực tế thành công: {phone} (attempt {attempt})")
                    break
            except Exception as e:
                log.warning(f"  Poll số điện thoại thất bại (attempt {attempt}): {e}")
        
        if not phone or "xin số" in phone or not any(c.isdigit() for c in phone):
            log.error("❌ Không lấy được số điện thoại thực tế từ API sau 18s — đang hủy số hoàn tiền...")
            try:
                requests.get(f"{_BASE}/api/ext/cancel", params={"apikey": apikey, "pkey": pkey}, timeout=10)
            except Exception as ce:
                log.warning(f"  Không thể hủy số: {ce}")
            raise RuntimeError("Không lấy được số điện thoại thực tế từ API!")

    log.info(f"✅ Phone: {phone} | pkey: {pkey[:12]}... | price: {data.get('price', 0)}")
    return {
        "phone":      phone,
        "pkey":       pkey,
        "price":      data.get("price", 0),
        "balance":    data.get("balance", 0),
        "expires_at": data.get("expires_at", 0),
    }

def poll_sms_otp(
    pkey: str,
    timeout: int = 300,
    poll_interval: int = 4,
) -> str | None:
    """
    Poll getSms until OTP is received or timeout is reached.
    """
    apikey = _get_apikey()
    deadline = time.time() + timeout
    log.info(f"⏳ Poll OTP | pkey: {pkey[:12]}... | timeout: {timeout}s")

    while time.time() < deadline:
        try:
            resp = requests.get(
                f"{_BASE}/api/ext/getSms",
                params={"apikey": apikey, "pkey": pkey},
                timeout=10,
            )
            data = resp.json()

            otp = data.get("otp", "")
            state = data.get("state", "")
            log.debug(f"  getSms: state='{state}' otp='{otp}'")

            if otp and state == "Hoàn thành":
                log.info(f"✅ SMS OTP: {otp}")
                return otp

        except Exception as e:
            log.warning(f"  getSms lỗi: {e}")

        remaining = int(deadline - time.time())
        if remaining <= 0:
            break
        # Chờ ngắt quãng để phản hồi nút STOP ngay lập tức
        import src.config as config
        stop_requested = False
        for _ in range(int(poll_interval * 2)):
            if config.STOP_FLAG:
                stop_requested = True
                break
            time.sleep(0.5)
        if stop_requested:
            log.warning("🛑 Nhận lệnh STOP, dừng chờ OTP SMS.")
            break

    log.warning(f"⏰ Timeout {timeout}s — không nhận được SMS OTP")
    return None

def cancel(pkey: str) -> bool:
    """Cancel order and refund if no OTP received."""
    try:
        apikey = _get_apikey()
        resp = requests.get(
            f"{_BASE}/api/ext/cancel",
            params={"apikey": apikey, "pkey": pkey},
            timeout=10,
        )
        data = resp.json()
        if data.get("status") == "success":
            log.info(f"✅ Hủy số thành công | balance: {data.get('balance', '?')}")
            return True
        log.warning(f"Hủy số thất bại: {data.get('message', data)}")
    except Exception as e:
        log.warning(f"cancel lỗi: {e}")
    return False
