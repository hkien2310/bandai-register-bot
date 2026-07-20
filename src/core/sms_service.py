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
_pre_fetched_lock = threading.Lock()

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

def _get_apikey(force_refresh: bool = False) -> str:
    """Get apikey from cache or API. Thread-safe."""
    global _apikey, _apikey_expires
    
    with _apikey_lock:
        now = time.time()
        
        if not force_refresh:
            # 1. Memory cache check
            if _apikey and now < _apikey_expires - 300:
                return _apikey

            # 2. Disk cache check (từ config.json)
            try:
                # Reload config.json to get the latest changes (nếu user sửa tay)
                if config.CONFIG_FILE.exists():
                    with open(config.CONFIG_FILE, "r", encoding="utf-8") as f:
                        config._cfg = json.load(f)

                file_key = config._cfg.get("sms_api_key", "")
                file_expires_raw = config._cfg.get("sms_api_key_expires", 0.0)
                
                if isinstance(file_expires_raw, str) and file_expires_raw:
                    try:
                        import datetime
                        dt = datetime.datetime.strptime(file_expires_raw, "%H:%M:%S %d/%m/%Y")
                        file_expires = dt.timestamp()
                    except:
                        file_expires = time.time() + 31536000
                elif not file_expires_raw and file_key:
                    # Nếu user điền key nhưng không điền hạn, mặc định cho sống 1 năm
                    file_expires = time.time() + 31536000
                else:
                    file_expires = file_expires_raw / 1000.0 if file_expires_raw > 1e10 else file_expires_raw
                
                if file_key and now < file_expires - 300:
                    _apikey = file_key
                    _apikey_expires = file_expires
                    return _apikey
            except Exception as e:
                log.warning(f"Không đọc được cache apikey từ config.json: {e}")

        # 3. Request new apikey
        if not config.SMS_USERNAME or not config.SMS_PASSWORD:
            raise RuntimeError("SMS_USERNAME / SMS_PASSWORD chưa cấu hình trong config.json")

        log.info("Lấy SMS apikey mới từ API...")
        resp = requests.post(
            f"{_BASE}/api/ext/getKey",
            json={"username": config.SMS_USERNAME, "password": config.SMS_PASSWORD},
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "success":
            raise RuntimeError(f"getKey thất bại: {data}")

        _apikey = data["apikey"]
        _apikey_expires = data.get("expires_at", 0.0) / 1000.0
        
        try:
            # Lưu file_expires dưới dạng string như user muốn
            expires_str = time.strftime('%H:%M:%S %d/%m/%Y', time.localtime(_apikey_expires))
            # Loại bỏ số 0 ở tháng/ngày nếu có để giống 12/7/2026
            expires_str = expires_str.replace('/0', '/')
            
            # Ghi trực tiếp vào config._cfg và lưu ra config.json
            config._cfg["sms_api_key"] = _apikey
            config._cfg["sms_api_key_expires"] = expires_str
            with open(config.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config._cfg, f, indent=4, ensure_ascii=False)
            log.info("Đã lưu SMS apikey mới vào config.json.")
        except Exception as e:
            log.warning(f"Không ghi được file config.json: {e}")

        expires_log = time.strftime('%H:%M:%S %d/%m/%Y', time.localtime(_apikey_expires)).replace('/0', '/')
        log.info(f"✅ Apikey OK (expires at: {expires_log})")
        return _apikey

def invalidate_apikey():
    """Clear memory and disk cache of apikey."""
    global _apikey, _apikey_expires
    with _apikey_lock:
        _apikey = ""
        _apikey_expires = 0.0
        try:
            if "sms_api_key" in config._cfg:
                config._cfg["sms_api_key"] = ""
            if "sms_api_key_expires" in config._cfg:
                config._cfg["sms_api_key_expires"] = ""
            
            with open(config.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config._cfg, f, indent=4, ensure_ascii=False)
            log.info("🧹 Đã xoá cache API Key do nghi ngờ bị lỗi hoặc hết hạn.")
        except Exception as e:
            log.warning(f"Không xóa được cache apikey trong config.json: {e}")

def check_balance(force_refresh=False) -> int:
    """Check SMS API balance."""
    try:
        apikey = _get_apikey(force_refresh=force_refresh)
        resp = requests.get(
            f"{_BASE}/api/ext/balance",
            params={"apikey": apikey},
            headers=_HEADERS,
            timeout=10,
        )
        try:
            data = resp.json()
        except Exception as json_e:
            log.error(f"❌ Phản hồi không phải JSON: {resp.status_code} - {resp.text[:200]}")
            raise json_e
        if data.get("status") == "success":
            balance = data["balance"]
            log.info(f"💰 Số dư SMS: {balance:,} điểm/yên")
            return balance
        else:
            msg = data.get("msg", "") or data.get("message", "")
            is_key_error = any(x in msg.lower() for x in ["api key", "hết hạn", "hợp lệ", "invalid", "expire"])
            if is_key_error:
                invalidate_apikey()
                if not force_refresh:
                    log.info("API Key hết hạn hoặc không hợp lệ, thử lấy lại key mới...")
                    return check_balance(force_refresh=True)
            log.error(f"❌ Lỗi API SMS: {data}")
    except Exception as e:
        log.error(f"❌ Lỗi khi lấy số dư: {e}")
    return -1

def order_phone(
    country: str | None = None,
    service_id: str | None = None,
    server: str | None = None,
    force_api: bool = False,
) -> dict:
    """
    Order phone number. Poll until phone number is ready.
    """
    if getattr(config, "USE_PRE_FETCHED_NUMBERS", False) and not force_api:
        pre_fetched_path = config.DATA_DIR / "pre_fetched_numbers.json"
        with _pre_fetched_lock:
            if pre_fetched_path.exists():
                try:
                    with open(pre_fetched_path, "r", encoding="utf-8") as f:
                        numbers = json.load(f)
                    if numbers and isinstance(numbers, list) and len(numbers) > 0:
                        now = time.time() * 1000
                        valid_num = None
                        for num in numbers:
                            if not num.get("is_used", False):
                                num["is_used"] = True
                                expires_at = num.get("expires_at", 0)
                                # Kiểm tra xem số còn hạn ít nhất 2 phút không
                                if expires_at > now + 120000:
                                    valid_num = num
                                    break
                                else:
                                    log.warning(f"📱 Số {num.get('phone')} đã quá hạn, bỏ qua.")
                        
                        unused_count = sum(1 for n in numbers if not n.get("is_used", False))
                        
                        with open(pre_fetched_path, "w", encoding="utf-8") as f:
                            json.dump(numbers, f, indent=4)
                            
                        if valid_num:
                            log.info(f"📱 Sử dụng số lấy trước: {valid_num.get('phone')} (còn {unused_count} số chưa dùng)")
                            return valid_num
                        else:
                            log.warning("📱 Hết số lấy trước hợp lệ, chuyển sang gọi API trực tiếp...")
                except Exception as e:
                    log.error(f"Lỗi đọc pre_fetched_numbers.json: {e}")

    def _do_order(force=False):
        apikey = _get_apikey(force_refresh=force)
        params = {
            "apikey":    apikey,
            "serviceId": service_id or config.SMS_SERVICE_ID,
            "server":    server     or config.SMS_SERVER,
            "country":   country    or config.SMS_COUNTRY,
        }
        resp = requests.get(f"{_BASE}/api/ext/order", params=params, headers=_HEADERS, timeout=15)
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            try:
                err_data = resp.json()
                log.error(f"HTTP {resp.status_code} Error: {err_data}")
                return err_data, params
            except Exception:
                pass
            raise e
        return resp.json(), params

    log.info(f"📱 Order phone | country={country or config.SMS_COUNTRY} serviceId={service_id or config.SMS_SERVICE_ID}")
    data, params = _do_order()

    if data.get("status") != "success":
        msg = data.get("message", "") or data.get("msg", "")
        is_key_error = any(x in msg.lower() for x in ["api key", "hết hạn", "hợp lệ", "invalid", "expire"])
        if is_key_error:
            invalidate_apikey()
            if not force:
                log.info(f"order thất bại do key ({msg}). Thử lấy lại API key mới...")
                data, params = _do_order(force=True)
                if data.get("status") != "success":
                    raise RuntimeError(f"order thất bại: {data.get('message', data)}")
            else:
                raise RuntimeError(f"order thất bại: {data.get('message', data)}")
        else:
            raise RuntimeError(f"order thất bại: {data.get('message', data)}")
    
    apikey = params["apikey"]

    pkey = data["pkey"]
    phone = data.get("phone", "").strip()

    # If phone is not ready, poll getSms to retrieve the actual number
    if not phone or "xin số" in phone or not any(c.isdigit() for c in phone):
        log.info("📱 Số điện thoại chưa sẵn sàng, đang poll getSms để lấy số thực tế...")
        max_attempts = 12
        for attempt in range(1, max_attempts + 1):
            time.sleep(10)
            try:
                get_resp = requests.get(
                    f"{_BASE}/api/ext/getSms",
                    params={"apikey": apikey, "pkey": pkey},
                    headers=_HEADERS,
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
            log.error("❌ Không lấy được số điện thoại thực tế từ API sau 120s — đang hủy số hoàn tiền...")
            try:
                requests.get(f"{_BASE}/api/ext/cancel", params={"apikey": apikey, "pkey": pkey}, headers=_HEADERS, timeout=10)
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
                headers=_HEADERS,
                timeout=10,
            )
            data = resp.json()

            if data.get("status") == "error":
                msg = data.get("msg", "") or data.get("message", "")
                is_key_error = any(x in msg.lower() for x in ["api key", "hết hạn", "hợp lệ", "invalid", "expire"])
                if is_key_error:
                    invalidate_apikey()
                    log.info("API Key hết hạn hoặc không hợp lệ khi poll OTP, đang lấy lại key mới...")
                    apikey = _get_apikey(force_refresh=True)
                    continue

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
            headers=_HEADERS,
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
