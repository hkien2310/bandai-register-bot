import gspread
import threading
from datetime import datetime
from google.oauth2.service_account import Credentials
import src.config as config
from src.utils.logger import get_logger

log = get_logger("google_sheets")

class GoogleSheetsManager:
    def __init__(self):
        self.lock = threading.Lock()
        
        if not config.GOOGLE_SHEET_ID:
            log.error("Thiếu GOOGLE_SHEET_ID trong config.json")
            self.client = None
            return

        try:
            from src.embedded_credentials import SECRETS
            credentials_info = SECRETS.get("CREDENTIALS_DICT")
        except ImportError:
            credentials_info = None

        try:
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            
            if credentials_info:
                credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
            else:
                import sys
                if getattr(sys, 'frozen', False):
                    cred_path = config.BUNDLE_DIR / "data" / "credentials.json"
                else:
                    cred_path = config.DATA_DIR / "credentials.json"
                    
                if not cred_path.exists():
                    log.error(f"Không tìm thấy file credentials tại {cred_path}")
                    self.client = None
                    return
                credentials = Credentials.from_service_account_file(str(cred_path), scopes=scopes)

            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open_by_key(config.GOOGLE_SHEET_ID)
            
            # Khởi tạo các tabs (tự động tạo nếu chưa có)
            self.mails_sheet = self._get_or_create_worksheet("Mails", ["Email", "Status", "Updated At", "DOB", "Prefecture"])
            self.proxies_sheet = self._get_or_create_worksheet("Proxies", ["Proxy", "Status"])
            
            self.accounts_columns = [
                "Email", "Bandai Password", "Namco Password", "Nickname",
                "Phone", "BNID", "Proxy Used", "Status", "Created At", "Error Details",
                "Data Usage (MB)", "DOB", "Location", "Link Đã Mua",
                "Họ (Kanji)", "Tên (Kanji)", "Họ (Kana)", "Tên (Kana)", 
                "Mã bưu điện", "Tỉnh/Thành", "Quận/Huyện", "Địa chỉ", "Tòa nhà"
            ]
            self.accounts_sheet = self._get_or_create_worksheet("Accounts", self.accounts_columns)
            
            log.info("✅ Kết nối Google Sheets thành công!")
            
            # Khôi phục các email đang PROCESSING (do tiến trình cũ bị crash/ngắt)
            self.reset_processing_emails()
        except Exception as e:
            log.error(f"❌ Lỗi kết nối Google Sheets: {e}")
            self.client = None

    def _get_or_create_worksheet(self, title, headers):
        try:
            sheet = self.spreadsheet.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            sheet = self.spreadsheet.add_worksheet(title=title, rows="1000", cols=str(len(headers)))
            sheet.append_row(headers)
            log.info(f"Tạo mới sheet {title}")
        return sheet

    def is_connected(self):
        return self.client is not None
        
    def reset_processing_emails(self):
        if not self.is_connected():
            return
            
        try:
            all_values = self.mails_sheet.get_all_values()
            if len(all_values) <= 1:
                return
            
            headers = all_values[0]
            try:
                status_idx = headers.index("Status")
            except ValueError:
                return
            
            updates = []
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            for row_idx_0_based, row in enumerate(all_values[1:]):
                row_idx = row_idx_0_based + 2
                status = row[status_idx].strip().upper() if len(row) > status_idx else ""
                
                if status == "PROCESSING":
                    # Cột B là Status, C là Updated At
                    updates.append({
                        'range': f'B{row_idx}:C{row_idx}',
                        'values': [['PENDING', now_str]]
                    })
            
            if updates:
                self.mails_sheet.batch_update(updates)
                log.info(f"🔄 Đã khôi phục {len(updates)} emails từ PROCESSING về PENDING do bot bị tắt đột ngột trước đó.")
        except Exception as e:
            log.error(f"Lỗi reset PROCESSING emails: {e}")

    def get_active_proxies(self) -> list:
        if not self.is_connected():
            return []
        try:
            records = self.proxies_sheet.get_all_records()
            # Lọc các proxy có Status là ACTIVE hoặc rỗng
            proxies = [str(r.get("Proxy")).strip() for r in records if r.get("Proxy") and str(r.get("Status", "")).upper() in ["ACTIVE", ""]]
            log.info(f"Đã load {len(proxies)} proxies từ Google Sheets")
            return proxies
        except Exception as e:
            log.error(f"Lỗi đọc proxies từ Sheets: {e}")
            return []

    def _parse_email_combo(self, raw: str) -> dict:
        """Tách chuỗi combo 'email|pass|token|...' thành dict."""
        parts = raw.strip().split("|")
        result = {"email": parts[0].strip(), "raw_email": raw.strip()}
        if len(parts) >= 2 and parts[1].strip():
            result["email_password"] = parts[1].strip()
        return result

    def get_pending_emails(self, batch_size=100) -> list:
        if not self.is_connected():
            return []
        
        with self.lock:
            try:
                # Đọc toàn bộ dữ liệu (trừ header)
                all_values = self.mails_sheet.get_all_values()
                if len(all_values) <= 1:
                    return []
                
                headers = all_values[0]
                pending_emails = []
                updates = [] # Danh sách các ô cần cập nhật thành PROCESSING
                
                # Tìm index của các cột
                try:
                    email_idx = headers.index("Email")
                    status_idx = headers.index("Status")
                except ValueError:
                    log.error("Sheet Mails thiếu cột Email hoặc Status")
                    return []

                dob_idx = headers.index("DOB") if "DOB" in headers else -1
                prefecture_idx = headers.index("Prefecture") if "Prefecture" in headers else -1

                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                for row_idx_0_based, row in enumerate(all_values[1:]):
                    row_idx = row_idx_0_based + 2 # Do bỏ header và gspread dùng index 1-based
                    
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
                
                log.info(f"Đã lấy {len(pending_emails)} emails từ Sheets (sẽ update PROCESSING khi từng acc thực sự chạy)")
                return pending_emails
                
            except Exception as e:
                log.error(f"Lỗi đọc/cập nhật emails từ Sheets: {e}")
                return []

    def update_email_status(self, email: str, new_status: str):
        if not self.is_connected():
            return
        
        with self.lock:
            try:
                # Phải tìm dòng chứa email này (email ở đây có thể là raw_email)
                cell = self.mails_sheet.find(email)
                if cell:
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.mails_sheet.update(f"B{cell.row}:C{cell.row}", [[new_status, now_str]])
            except Exception as e:
                if "CellNotFound" in str(type(e)):
                    log.warning(f"Không tìm thấy email {email} trong sheet Mails để cập nhật status")
                else:
                    log.error(f"Lỗi khi update status cho email {email}: {e}")

    def append_account(self, data: dict):
        if not self.is_connected():
            return
        
        row = []
        for col in self.accounts_columns:
            # Map tên cột CSV cũ sang tên cột Sheet nếu cần (hoặc truyền data chuẩn)
            # data thường có key dạng chữ thường: email, bandai_password...
            # Nên ta map lại
            key_map = {
                "Email": "email",
                "Bandai Password": "bandai_password",
                "Namco Password": "namco_password",
                "Nickname": "nickname",
                "DOB": "birthday",
                "Ngày sinh": "birthday",
                "Birthday": "birthday",
                "Location": "prefecture",
                "Tỉnh thành": "prefecture",
                "Prefecture": "prefecture",
                "Phone": "phone",
                "BNID": "bnid_user_code",
                "Proxy Used": "proxy_used",
                "Status": "status",
                "Created At": "created_at",
                "Error Details": "error_details",
                "Data Usage (MB)": "data_usage_mb",
                "Link Đã Mua": "purchased_links"
            }
            key = key_map.get(col, col.lower())
            
            val = data.get(key, "")
            # Điền mặc định created_at nếu thành công
            if key == "created_at" and not val and data.get("status") == "SUCCESS":
                val = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row.append(str(val))
            
        with self.lock:
            try:
                email = data.get('email', '')
                try:
                    cell = self.accounts_sheet.find(email)
                    if cell:
                        start_col = "A"
                        end_col = chr(ord("A") + len(self.accounts_columns) - 1)
                        cell_range = f"{start_col}{cell.row}:{end_col}{cell.row}"
                        self.accounts_sheet.update(cell_range, [row])
                        log.info(f"Đã CẬP NHẬT kết quả acc {email} lên Google Sheets (Dòng {cell.row})")
                    else:
                        raise Exception("CellNotFound_Custom")
                except Exception as e:
                    if "CellNotFound" in str(type(e)) or "CellNotFound_Custom" in str(e):
                        self.accounts_sheet.append_row(row)
                        log.info(f"Đã THÊM MỚI kết quả acc {email} lên Google Sheets")
                    else:
                        raise e
            except Exception as e:
                log.error(f"Lỗi khi ghi acc {data.get('email')} lên Sheets: {e}")
                # Backup vào file local nếu lỗi
                self._backup_to_local(row)
                
    def _backup_to_local(self, row: list):
        import csv
        backup_file = config.DATA_DIR / "accounts_backup.csv"
        try:
            with open(backup_file, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                if backup_file.stat().st_size == 0:
                    writer.writerow(self.accounts_columns)
                writer.writerow(row)
            log.info(f"Đã backup acc vào {backup_file}")
        except Exception as e:
            log.error(f"Không thể ghi file backup local: {e}")

    def get_account_status(self, email: str) -> str | None:
        """Tra cứu status của email trên sheet Accounts. Trả về status hoặc None nếu chưa có."""
        if not self.is_connected():
            return None
        with self.lock:
            try:
                cell = self.accounts_sheet.find(email)
                if cell:
                    row = self.accounts_sheet.row_values(cell.row)
                    # Status ở cột thứ 8 (index 7)
                    status_idx = self.accounts_columns.index("Status")
                    if len(row) > status_idx:
                        return row[status_idx].strip().upper()
                return None
            except Exception as e:
                if "CellNotFound" not in str(type(e)):
                    log.warning(f"Lỗi tra cứu status cho {email}: {e}")
                return None

    def get_accounts_for_purchase(self, product_link: str, required_count: int) -> list:
        """Đọc sheet Accounts, lọc các account SUCCESS và chưa mua product_link."""
        if not self.is_connected():
            return []
            
        with self.lock:
            try:
                all_values = self.accounts_sheet.get_all_values()
                if len(all_values) <= 1:
                    return []
                    
                headers = all_values[0]
                try:
                    email_idx = headers.index("Email")
                    status_idx = headers.index("Status")
                except ValueError:
                    log.error("Sheet Accounts thiếu cột Email hoặc Status")
                    return []
                    
                purchased_idx = headers.index("Link Đã Mua") if "Link Đã Mua" in headers else -1
                
                # Cần lấy cả thông tin account để login
                password_idx = headers.index("Bandai Password") if "Bandai Password" in headers else -1
                if password_idx == -1:
                    log.error("Thiếu cột Bandai Password")
                    return []
                    
                eligible_accounts = []
                
                for row_idx_0_based, row in enumerate(all_values[1:]):
                    # Bỏ qua các row trống
                    if not row or len(row) <= email_idx:
                        continue
                        
                    email = row[email_idx].strip()
                    status = row[status_idx].strip().upper() if len(row) > status_idx else ""
                    
                    if not email or status != "SUCCESS":
                        continue
                        
                    # Lấy link đã mua
                    purchased_links = row[purchased_idx].strip() if purchased_idx != -1 and len(row) > purchased_idx else ""
                    
                    # Kiểm tra xem link hiện tại đã có trong danh sách chưa
                    # Bandai giới hạn cùng event. Mỗi ngày là 1 event khác nhau. Base code gồm Mã chính + Ngày (Ví dụ: ECCL00000036_20260711)
                    import re
                    base_code = product_link
                    m = re.search(r'/([A-Z0-9]+_[0-9]+)_[0-9]+\.html', product_link)
                    if m:
                        base_code = m.group(1)
                        
                    if product_link not in purchased_links and base_code not in purchased_links:
                        
                        # Mapping dữ liệu Shipping
                        def get_val(col_name):
                            try:
                                idx = headers.index(col_name)
                                return row[idx].strip() if len(row) > idx else ""
                            except ValueError:
                                return ""
                                
                        acc_data = {
                            "email": email,
                            "password": row[password_idx].strip() if len(row) > password_idx else "",
                            "row_index": row_idx_0_based + 2, # Lưu row index để dễ update
                            "purchased_links": purchased_links,
                            "proxy": get_val("Proxy"),
                            # Shipping Address & Info
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
                            
                log.info(f"Đã lọc được {len(eligible_accounts)} accounts đủ điều kiện mua hàng.")
                return eligible_accounts
                
            except Exception as e:
                log.error(f"Lỗi đọc tài khoản mua hàng từ Sheets: {e}")
                return []

    def update_purchased_link(self, email: str, new_link: str):
        """Cập nhật Link Đã Mua cho một account sau khi mua thành công."""
        if not self.is_connected():
            return
            
        with self.lock:
            try:
                cell = self.accounts_sheet.find(email)
                if not cell:
                    return
                
                row = self.accounts_sheet.row_values(cell.row)
                
                # Tìm index cột Link Đã Mua
                headers = self.accounts_sheet.row_values(1)
                if "Link Đã Mua" not in headers:
                    log.warning("Sheet Accounts chưa có header 'Link Đã Mua', đang tự động thêm...")
                    try:
                        self.accounts_sheet.add_cols(1)
                    except:
                        pass
                    self.accounts_sheet.update_cell(1, len(headers) + 1, "Link Đã Mua")
                    headers.append("Link Đã Mua")
                    
                col_idx = headers.index("Link Đã Mua")
                
                current_links = row[col_idx].strip() if len(row) > col_idx else ""
                if current_links:
                    updated_links = current_links + "\n" + new_link
                else:
                    updated_links = new_link
                    
                self.accounts_sheet.update_cell(cell.row, col_idx + 1, updated_links)
                log.info(f"Đã cập nhật Link Đã Mua cho account {email}")
                
            except Exception as e:
                log.error(f"Lỗi cập nhật Link Đã Mua cho {email}: {e}")

    def update_account_address(self, acc: dict):
        """Cập nhật lại các trường địa chỉ nếu có thay đổi"""
        if not self.is_connected(): return
        with self.lock:
            try:
                cell = self.accounts_sheet.find(acc['email'])
                if not cell: return
                
                headers = self.accounts_sheet.row_values(1)
                
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
                
                # Cập nhật từng ô (chậm một chút nhưng an toàn tuyệt đối)
                for k, header in mapping.items():
                    if header in headers:
                        col_idx = headers.index(header) + 1
                        val = acc.get(k, "")
                        self.accounts_sheet.update_cell(cell.row, col_idx, val)
                
                log.info(f"Đã cập nhật thông tin địa chỉ về Sheet cho {acc['email']}")
            except Exception as e:
                log.error(f"Lỗi cập nhật địa chỉ cho {acc['email']}: {e}")
