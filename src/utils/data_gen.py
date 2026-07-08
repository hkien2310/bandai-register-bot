import random
import hashlib
from datetime import datetime, timedelta
import src.config as config

# Seed random using email to ensure consistency for retries
def get_seeded_random(seed_str: str) -> random.Random:
    hash_object = hashlib.md5(seed_str.encode("utf-8"))
    seed_int = int(hash_object.hexdigest(), 16)
    return random.Random(seed_int)

def generate_birthday(email: str) -> str:
    """Sinh ngày sinh ngẫu nhiên từ 19 đến 40 tuổi (để qua tuổi 18). Dạng YYYY-MM-DD."""
    r = get_seeded_random(email)
    years_ago = r.randint(19, 40)
    days_offset = r.randint(0, 365)
    
    birth_date = datetime.now() - timedelta(days=years_ago * 365.25 + days_offset)
    return birth_date.strftime("%Y-%m-%d")

def generate_nickname(email: str) -> str:
    """Sinh nickname ngẫu nhiên từ danh sách tên phổ biến."""
    r = get_seeded_random(email)
    first_names = [
        "Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito", "Yamamoto",
        "Nakamura", "Kobayashi", "Kato", "Yoshida", "Yamada", "Sasaki", "Yamaguchi",
        "Saito", "Matsumoto", "Inoue", "Kimura", "Hayashi", "Shimizu", "Koji",
        "Hiro", "Ken", "Shin", "Taku", "Yuki", "Haru", "Ren", "Sho", "Taiga"
    ]
    suffixes = ["kun", "chan", "san", "99", "123", "parks", "bn", "jp", "88"]
    
    name = r.choice(first_names)
    suffix = r.choice(suffixes)
    return f"{name}{suffix}"

def generate_password(email: str) -> str:
    """Trả về mật khẩu mặc định chung từ cấu hình."""
    return config.DEFAULT_PASSWORD

