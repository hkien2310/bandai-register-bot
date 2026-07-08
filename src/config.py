import json
import shutil
from pathlib import Path
import sys

# Xác định ROOT_DIR (thư mục gốc)
if getattr(sys, 'frozen', False):
    _exe_dir = Path(sys.executable).parent
    BUNDLE_DIR = Path(sys._MEIPASS)
    # macOS .app bundle: executable ở NamcoBot.app/Contents/MacOS/NamcoBot
    # Config nằm cạnh NamcoBot.app, cần đi lên 3 cấp
    if _exe_dir.name == "MacOS" and _exe_dir.parent.name == "Contents":
        ROOT_DIR = _exe_dir.parent.parent.parent  # thư mục chứa .app
    else:
        ROOT_DIR = _exe_dir  # Windows: exe nằm thẳng cạnh config
else:
    ROOT_DIR = Path(__file__).parent.parent
    BUNDLE_DIR = ROOT_DIR

def _extract_if_missing(rel_path: str):
    """Extract file từ bundle ra cạnh exe nếu chưa có."""
    dest = ROOT_DIR / rel_path
    src = BUNDLE_DIR / rel_path
    if not dest.exists() and src.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))

# Lần đầu chạy: tự tạo config files cạnh exe
if getattr(sys, 'frozen', False):
    _extract_if_missing("config.json")

# Load config.json (nguồn duy nhất)
import os
config_name = os.environ.get("CONFIG_FILE", "config.json")
CONFIG_FILE = ROOT_DIR / config_name
if CONFIG_FILE.exists():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        _cfg = json.load(f)
else:
    _cfg = {}

def _get(key, default=""):
    return _cfg.get(key, default)

# Load secrets from data/sheet_config.json (will be bundled by PyInstaller)
APP_SECRETS_FILE = BUNDLE_DIR / "data" / "sheet_config.json"
app_secrets = {}
if APP_SECRETS_FILE.exists():
    try:
        with open(APP_SECRETS_FILE, "r", encoding="utf-8") as f:
            app_secrets = json.load(f)
    except Exception as e:
        print(f"Lỗi đọc sheet_config.json: {e}")

# Paths
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Bot settings
BROWSER_PATH        = _get("browser_path", "")
HEADLESS            = _get("headless", False)
GOOGLE_SHEET_ID     = app_secrets.get("GOOGLE_SHEET_ID", "18qwM6DmmQ9c8S0PoY1ureJqMo3UOBkQfDUBy3lOr3EE")
WORKER_COUNT        = _get("worker_count", 1)
EMAIL_OTP_TIMEOUT   = _get("email_otp_timeout", 120)
SMS_OTP_TIMEOUT     = _get("sms_otp_timeout", 300)
DEFAULT_PASSWORD    = _get("default_password", "Namco2025!")
DEFAULT_GENDER      = _get("default_gender", "回答しない")
DEFAULT_PREFECTURE  = _get("default_prefecture", "愛知県")
DEFAULT_DOB         = _get("default_dob", "1990-11-12")
DEFAULT_NICKNAME    = _get("default_nickname", "ヴオン・ドゥック・タイン")
KEEP_BROWSER_OPEN   = _get("keep_browser_open", False)

# Email config
EMAIL_MODE          = _get("email_mode", "alias")
CATCHALL_INBOX      = _get("catchall_inbox", "")
CATCHALL_PASSWORD   = _get("catchall_password", "")
CATCHALL_DOMAIN     = _get("catchall_domain", "")
CATCHALL_EMAIL_PREFIX = _get("catchall_email_prefix", "acc")

# SMS config
SMS_ENABLED         = _get("sms_enabled", True)
SMS_BASE_URL        = _get("sms_base_url", "https://northdinhjpn.online")
SMS_API_KEY         = _get("sms_api_key", "")
SMS_USERNAME        = _get("sms_username", "")
SMS_PASSWORD        = _get("sms_password", "")
SMS_SERVICE_ID      = str(_get("sms_service_id", "4005"))
SMS_COUNTRY         = _get("sms_country", "jpn")
SMS_SERVER          = str(_get("sms_server", "2"))

# Proxy config
USE_PROXY               = _get("use_proxy", True)
MAX_ACCOUNTS_PER_PROXY  = int(_get("max_accounts_per_proxy", 10))

# Biến cờ hiệu toàn cục để ngắt bot (Stop button)
STOP_FLAG = False
