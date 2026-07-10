import csv
import os
import threading
from datetime import datetime
from pathlib import Path
import src.config as config
from src.utils.logger import get_logger

log = get_logger("csv_manager")

class CsvManager:
    def __init__(self):
        self.lock = threading.Lock()
        
        self.data_dir = config.DATA_DIR
        self.data_dir.mkdir(exist_ok=True)
        
        self.emails_csv = self.data_dir / "emails.csv"
        self.proxies_csv = self.data_dir / "proxies.csv"
        self.accounts_csv = self.data_dir / "accounts.csv"
        
        self.emails_headers = ["Email", "Status", "Updated At", "DOB", "Prefecture"]
        self.proxies_headers = ["Proxy", "Status"]
        self.accounts_headers = [
            "Email", "Bandai Password", "Namco Password", "Nickname",
            "Phone", "BNID", "Proxy Used", "Status", "Created At", "Error Details",
            "Data Usage (MB)", "DOB", "Location", "Link Đã Mua",
            "Họ (Kanji)", "Tên (Kanji)", "Họ (Kana)", "Tên (Kana)", 
            "Mã bưu điện", "Tỉnh/Thành", "Quận/Huyện", "Địa chỉ", "Tòa nhà"
        ]
        
        self._init_csv_files()
        
        log.info("✅ Đã khởi tạo CSV Manager thành công!")
        
        # Khôi phục các email đang PROCESSING
        self.reset_processing_emails()

    def _init_csv_files(self):
        """Khởi tạo file CSV nếu chưa tồn tại"""
        with self.lock:
            if not self.emails_csv.exists():
                self._write_row(self.emails_csv, self.emails_headers)
                log.info(f"Tạo mới file {self.emails_csv.name}")
                
            if not self.proxies_csv.exists():
                self._write_row(self.proxies_csv, self.proxies_headers)
                log.info(f"Tạo mới file {self.proxies_csv.name}")
                
            if not self.accounts_csv.exists():
                self._write_row(self.accounts_csv, self.accounts_headers)
                log.info(f"Tạo mới file {self.accounts_csv.name}")

    def _write_row(self, path: Path, row: list, mode="a"):
        with open(path, mode, newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(row)

    def _read_all(self, path: Path) -> list:
        if not path.exists():
            return []
        try:
            with open(path, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                return list(reader)
        except Exception as e:
            log.error(f"Lỗi đọc file {path.name}: {e}")
            return []

    def _write_all(self, path: Path, rows: list):
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerows(rows)
        except Exception as e:
            log.error(f"Lỗi ghi file {path.name}: {e}")

    def is_connected(self):
        return True
        
    def reset_processing_emails(self):
        with self.lock:
            rows = self._read_all(self.emails_csv)
            if len(rows) <= 1:
                return
            
            headers = rows[0]
            try:
                status_idx = headers.index("Status")
                updated_idx = headers.index("Updated At") if "Updated At" in headers else -1
            except ValueError:
                return
            
            changed = False
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            count = 0
            
            for row in rows[1:]:
                status = row[status_idx].strip().upper() if len(row) > status_idx else ""
                if status == "PROCESSING":
                    row[status_idx] = "PENDING"
                    if updated_idx != -1:
                        while len(row) <= updated_idx:
                            row.append("")
                        row[updated_idx] = now_str
                    changed = True
                    count += 1
            
            if changed:
                self._write_all(self.emails_csv, rows)
                log.info(f"🔄 Đã khôi phục {count} emails từ PROCESSING về PENDING do bot bị tắt đột ngột trước đó.")

    def get_active_proxies(self) -> list:
        with self.lock:
            rows = self._read_all(self.proxies_csv)
            if len(rows) <= 1:
                return []
            
            headers = rows[0]
            try:
                proxy_idx = headers.index("Proxy")
                status_idx = headers.index("Status")
            except ValueError:
                log.error("File proxies.csv thiếu cột Proxy hoặc Status")
                return []
            
            proxies = []
            for row in rows[1:]:
                proxy = row[proxy_idx].strip() if len(row) > proxy_idx else ""
                status = row[status_idx].strip().upper() if len(row) > status_idx else ""
                if proxy and status in ["ACTIVE", ""]:
                    proxies.append(proxy)
                    
            log.info(f"Đã load {len(proxies)} proxies từ {self.proxies_csv.name}")
            return proxies

    def _parse_email_combo(self, raw: str) -> dict:
        parts = raw.strip().split("|")
        result = {"email": parts[0].strip(), "raw_email": raw.strip()}
        if len(parts) >= 2 and parts[1].strip():
            result["email_password"] = parts[1].strip()
        return result

    def get_pending_emails(self, batch_size=100) -> list:
        with self.lock:
            rows = self._read_all(self.emails_csv)
            if len(rows) <= 1:
                return []
            
            headers = rows[0]
            try:
                email_idx = headers.index("Email")
                status_idx = headers.index("Status")
            except ValueError:
                log.error("File emails.csv thiếu cột Email hoặc Status")
                return []

            dob_idx = headers.index("DOB") if "DOB" in headers else -1
            prefecture_idx = headers.index("Prefecture") if "Prefecture" in headers else -1

            pending_emails = []

            for row in rows[1:]:
                raw_email = row[email_idx].strip() if len(row) > email_idx else ""
                status = row[status_idx].strip().upper() if len(row) > status_idx else ""
                
                if raw_email and status in ["", "PENDING", "FAIL", "FAILED", "ERROR", "HAS_BNID"]:
                    parsed = self._parse_email_combo(raw_email)
                    
                    if dob_idx != -1 and len(row) > dob_idx and row[dob_idx].strip():
                        parsed["dob"] = row[dob_idx].strip()
                    if prefecture_idx != -1 and len(row) > prefecture_idx and row[prefecture_idx].strip():
                        parsed["prefecture"] = row[prefecture_idx].strip()
                        
                    pending_emails.append(parsed)
                    
                    if len(pending_emails) >= batch_size:
                        break
            
            log.info(f"Đã lấy {len(pending_emails)} emails từ CSV (sẽ update PROCESSING khi từng acc thực sự chạy)")
            return pending_emails

    def update_email_status(self, email: str, new_status: str):
        with self.lock:
            rows = self._read_all(self.emails_csv)
            if len(rows) <= 1:
                return
            
            headers = rows[0]
            try:
                email_idx = headers.index("Email")
                status_idx = headers.index("Status")
                updated_idx = headers.index("Updated At") if "Updated At" in headers else -1
            except ValueError:
                return

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            changed = False
            
            for row in rows[1:]:
                raw_email = row[email_idx].strip() if len(row) > email_idx else ""
                if raw_email == email:
                    while len(row) <= max(status_idx, updated_idx):
                        row.append("")
                    row[status_idx] = new_status
                    if updated_idx != -1:
                        row[updated_idx] = now_str
                    changed = True
                    break
                    
            if changed:
                self._write_all(self.emails_csv, rows)

    def append_account(self, data: dict):
        with self.lock:
            rows = self._read_all(self.accounts_csv)
            if len(rows) == 0:
                rows.append(self.accounts_headers)
                
            headers = rows[0]
            
            key_map = {
                "Email": "email",
                "Bandai Password": "bandai_password",
                "Namco Password": "namco_password",
                "Nickname": "nickname",
                "DOB": "birthday",
                "Location": "prefecture",
                "Phone": "phone",
                "BNID": "bnid_user_code",
                "Proxy Used": "proxy_used",
                "Status": "status",
                "Created At": "created_at",
                "Error Details": "error_details",
                "Data Usage (MB)": "data_usage_mb",
                "Link Đã Mua": "purchased_links"
            }
            
            new_row = []
            for col in headers:
                key = key_map.get(col, col.lower())
                val = data.get(key, "")
                if key == "created_at" and not val and data.get("status") == "SUCCESS":
                    val = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_row.append(str(val))
                
            email_idx = headers.index("Email") if "Email" in headers else 0
            email = data.get('email', '')
            
            updated = False
            for i, row in enumerate(rows[1:]):
                if len(row) > email_idx and row[email_idx].strip() == email:
                    rows[i+1] = new_row
                    updated = True
                    log.info(f"Đã CẬP NHẬT kết quả acc {email} vào CSV")
                    break
                    
            if not updated:
                rows.append(new_row)
                log.info(f"Đã THÊM MỚI kết quả acc {email} vào CSV")
                
            self._write_all(self.accounts_csv, rows)

    def get_account_status(self, email: str) -> str | None:
        with self.lock:
            rows = self._read_all(self.accounts_csv)
            if len(rows) <= 1:
                return None
                
            headers = rows[0]
            if "Email" not in headers or "Status" not in headers:
                return None
                
            email_idx = headers.index("Email")
            status_idx = headers.index("Status")
            
            for row in rows[1:]:
                if len(row) > email_idx and row[email_idx].strip() == email:
                    if len(row) > status_idx:
                        return row[status_idx].strip().upper()
                    return ""
            return None

    def get_accounts_for_purchase(self, product_link: str, required_count: int) -> list:
        with self.lock:
            rows = self._read_all(self.accounts_csv)
            if len(rows) <= 1:
                return []
                
            headers = rows[0]
            try:
                email_idx = headers.index("Email")
                status_idx = headers.index("Status")
            except ValueError:
                return []
                
            purchased_idx = headers.index("Link Đã Mua") if "Link Đã Mua" in headers else -1
            password_idx = headers.index("Bandai Password") if "Bandai Password" in headers else -1
            
            if password_idx == -1:
                return []
                
            eligible_accounts = []
            
            import re
            base_code = product_link
            m = re.search(r'/([A-Z0-9]+_[0-9]+)_[0-9]+\.html', product_link)
            if m:
                base_code = m.group(1)
                
            for row_idx_0_based, row in enumerate(rows[1:]):
                if not row or len(row) <= email_idx:
                    continue
                    
                email = row[email_idx].strip()
                status = row[status_idx].strip().upper() if len(row) > status_idx else ""
                
                if not email or status != "SUCCESS":
                    continue
                    
                purchased_links = row[purchased_idx].strip() if purchased_idx != -1 and len(row) > purchased_idx else ""
                
                if product_link not in purchased_links and base_code not in purchased_links:
                    def get_val(col_name):
                        try:
                            idx = headers.index(col_name)
                            return row[idx].strip() if len(row) > idx else ""
                        except ValueError:
                            return ""
                            
                    acc_data = {
                        "email": email,
                        "password": row[password_idx].strip() if len(row) > password_idx else "",
                        "row_index": row_idx_0_based + 1,
                        "purchased_links": purchased_links,
                        "proxy": get_val("Proxy Used"),
                        "l_name": get_val("Họ (Kanji)"),
                        "f_name": get_val("Tên (Kanji)"),
                        "l_kana": get_val("Họ (Kana)"),
                        "f_kana": get_val("Tên (Kana)"),
                        "zip": get_val("Mã bưu điện"),
                        "addr1": get_val("Tỉnh/Thành"),
                        "addr2": get_val("Quận/Huyện"),
                        "addr_street": get_val("Địa chỉ"),
                        "addr_building": get_val("Tòa nhà"),
                        "tel": get_val("Phone")
                    }
                    eligible_accounts.append(acc_data)
                    
                    if len(eligible_accounts) >= required_count:
                        break
            
            return eligible_accounts

    def update_purchased_link(self, email: str, new_link: str):
        with self.lock:
            rows = self._read_all(self.accounts_csv)
            if len(rows) <= 1:
                return
                
            headers = rows[0]
            if "Email" not in headers:
                return
                
            email_idx = headers.index("Email")
            
            if "Link Đã Mua" not in headers:
                headers.append("Link Đã Mua")
                for r in rows[1:]:
                    r.append("")
                    
            col_idx = headers.index("Link Đã Mua")
            changed = False
            
            for row in rows[1:]:
                if len(row) > email_idx and row[email_idx].strip() == email:
                    while len(row) <= col_idx:
                        row.append("")
                        
                    current_links = row[col_idx].strip()
                    if current_links:
                        row[col_idx] = current_links + "\n" + new_link
                    else:
                        row[col_idx] = new_link
                    changed = True
                    break
                    
            if changed:
                self._write_all(self.accounts_csv, rows)
                log.info(f"Đã cập nhật Link Đã Mua cho account {email}")

    def update_account_address(self, acc: dict):
        with self.lock:
            rows = self._read_all(self.accounts_csv)
            if len(rows) <= 1: return
            
            headers = rows[0]
            if "Email" not in headers: return
            email_idx = headers.index("Email")
            
            mapping = {
                "l_name": "Họ (Kanji)",
                "f_name": "Tên (Kanji)",
                "l_kana": "Họ (Kana)",
                "f_kana": "Tên (Kana)",
                "zip": "Mã bưu điện",
                "addr1": "Tỉnh/Thành",
                "addr2": "Quận/Huyện",
                "addr_street": "Địa chỉ",
                "addr_building": "Tòa nhà",
                "tel": "Phone"
            }
            
            changed = False
            for row in rows[1:]:
                if len(row) > email_idx and row[email_idx].strip() == acc['email']:
                    for k, header in mapping.items():
                        if header in headers:
                            col_idx = headers.index(header)
                            while len(row) <= col_idx:
                                row.append("")
                            row[col_idx] = acc.get(k, "")
                    changed = True
                    break
                    
            if changed:
                self._write_all(self.accounts_csv, rows)
                log.info(f"Đã cập nhật thông tin địa chỉ vào CSV cho {acc['email']}")
