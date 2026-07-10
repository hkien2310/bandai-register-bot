"""
XlsxConnection — Service kết nối dữ liệu qua file XLSX local.

Thay thế hoàn toàn GoogleSheetsManager.
Giữ nguyên interface (method names & return types) để worker.py không cần sửa.

Cấu trúc file XLSX:
  Sheet "Mails"    — danh sách email đầu vào (đọc + cập nhật status)
  Sheet "Accounts" — kết quả đăng ký (ghi/upsert)
  Sheet "Proxies"  — danh sách proxy (tùy chọn)
"""

import threading
from pathlib import Path
from datetime import datetime

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

from src.utils.logger import get_logger

log = get_logger("xlsx_connection")

# ──────────────────────────────────────────────────────────────────────────────
# Header definitions (single source of truth for all output columns)
# ──────────────────────────────────────────────────────────────────────────────

MAILS_HEADERS    = ["email", "email_password", "dob", "prefecture", "nickname", "status"]
ACCOUNTS_HEADERS = [
    "email", "bandai_password", "namco_password", "nickname",
    "phone", "bnid_user_code", "proxy_used", "status", "created_at", "error_details"
]
PROXIES_HEADERS  = ["proxy", "status"]


class XlsxConnection:
    """Service đọc/ghi dữ liệu từ file XLSX local. Thread-safe."""

    def __init__(self, xlsx_path: str):
        self.xlsx_path = Path(xlsx_path) if xlsx_path else None
        self._lock = threading.Lock()
        self._connected = False

        if self.xlsx_path and self.xlsx_path.exists():
            try:
                wb = openpyxl.load_workbook(str(self.xlsx_path))
                self._ensure_sheets(wb)
                wb.save(str(self.xlsx_path))
                wb.close()
                self._connected = True
                log.info(f"✅ XlsxConnection: Kết nối thành công → {self.xlsx_path}")
            except Exception as e:
                log.error(f"❌ XlsxConnection: Không thể mở file XLSX: {e}")
        else:
            if self.xlsx_path:
                log.warning(f"⚠️ XlsxConnection: File không tồn tại: {self.xlsx_path}")
            else:
                log.warning("⚠️ XlsxConnection: Chưa cấu hình đường dẫn file XLSX.")

    # ──────────────────────────────────────────────────────────────────────────
    # Public: lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        return self._connected

    # ──────────────────────────────────────────────────────────────────────────
    # Public: Mails sheet
    # ──────────────────────────────────────────────────────────────────────────

    def get_pending_emails(self, batch_size: int = 50) -> list:
        """
        Đọc tối đa `batch_size` email có status PENDING (hoặc ô trống) từ sheet Mails.

        Cột email hỗ trợ 2 format:
          - Chỉ email:               user@hotmail.com
          - Pipe-separated (1 cột):  user@hotmail.com|password|token|uuid
            Field 1: email
            Field 2: email_password
            Field 3: ms_token (Microsoft refresh token, tùy chọn)
            Field 4: ms_uuid  (Microsoft account UUID, tùy chọn)

        Trả về list[dict].
        """
        with self._lock:
            try:
                wb = openpyxl.load_workbook(str(self.xlsx_path))
                ws = wb["Mails"]
                headers = self._get_headers(ws)

                results = []
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if len(results) >= batch_size:
                        break
                    row_dict = dict(zip(headers, row))
                    raw_email_cell = str(row_dict.get("email", "") or "").strip()
                    if not raw_email_cell:
                        continue
                    status = str(row_dict.get("status", "") or "").strip().upper()
                    if status in ("", "PENDING"):
                        # Parse pipe-separated format
                        parts = raw_email_cell.split("|")
                        email         = parts[0].strip()
                        email_password = parts[1].strip() if len(parts) > 1 else str(row_dict.get("email_password", "") or "").strip()
                        ms_token      = parts[2].strip() if len(parts) > 2 else ""
                        ms_uuid       = parts[3].strip() if len(parts) > 3 else ""

                        results.append({
                            "email": email,
                            "raw_email": raw_email_cell,  # giữ nguyên giá trị gốc để update status
                            "email_password": email_password,
                            "ms_token": ms_token,
                            "ms_uuid": ms_uuid,
                            "dob": str(row_dict.get("dob", "") or "").strip(),
                            "prefecture": str(row_dict.get("prefecture", "") or "").strip(),
                            "nickname": str(row_dict.get("nickname", "") or "").strip(),
                        })
                wb.close()
                log.info(f"📋 Đọc được {len(results)} email PENDING từ XLSX.")
                return results
            except Exception as e:
                log.error(f"❌ Lỗi đọc email từ XLSX: {e}")
                return []


    def update_email_status(self, email: str, status: str):
        """
        Cập nhật cột status trong sheet Mails.
        Tìm dòng theo email (hoặc raw pipe string nếu truyền vào).
        """
        email = str(email or "").strip()
        if not email:
            return
        with self._lock:
            try:
                wb = openpyxl.load_workbook(str(self.xlsx_path))
                ws = wb["Mails"]
                headers = self._get_headers(ws)
                status_col = self._col_index(headers, "status")
                email_col  = self._col_index(headers, "email")

                for row in ws.iter_rows(min_row=2):
                    cell_val = str(row[email_col].value or "").strip()
                    # Match theo raw value (pipe string) hoặc chỉ phần email trước |
                    cell_email = cell_val.split("|")[0].strip()
                    if cell_val == email or cell_email == email:
                        row[status_col].value = status
                        break

                wb.save(str(self.xlsx_path))
                wb.close()
                log.debug(f"📝 Cập nhật status '{status}' cho: {email}")
            except Exception as e:
                log.error(f"❌ Lỗi cập nhật email status: {e}")


    # ──────────────────────────────────────────────────────────────────────────
    # Public: Accounts sheet
    # ──────────────────────────────────────────────────────────────────────────

    def append_account(self, data: dict):
        """
        Upsert kết quả vào sheet Accounts theo email.
        Update nếu đã có, insert nếu chưa có.
        """
        email = str(data.get("email", "") or "").strip()
        if not email:
            return

        if not data.get("created_at") and data.get("status") == "SUCCESS":
            data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._lock:
            try:
                wb = openpyxl.load_workbook(str(self.xlsx_path))
                ws = wb["Accounts"]
                headers = self._get_headers(ws)
                email_col = self._col_index(headers, "email")

                target_row = None
                for row in ws.iter_rows(min_row=2):
                    if str(row[email_col].value or "").strip() == email:
                        target_row = row
                        break

                new_values = [data.get(h, "") or "" for h in ACCOUNTS_HEADERS]

                if target_row:
                    for i, val in enumerate(new_values):
                        target_row[i].value = val
                    log.info(f"📝 Cập nhật kết quả: {email} → {data.get('status')}")
                else:
                    ws.append(new_values)
                    log.info(f"📝 Thêm mới kết quả: {email} → {data.get('status')}")

                wb.save(str(self.xlsx_path))
                wb.close()
            except Exception as e:
                log.error(f"❌ Lỗi ghi Accounts vào XLSX: {e}")

    def get_account_status(self, email: str) -> str:
        """Kiểm tra email đã có trong Accounts chưa, trả về status hoặc rỗng."""
        email = str(email or "").strip()
        with self._lock:
            try:
                wb = openpyxl.load_workbook(str(self.xlsx_path), read_only=True)
                ws = wb["Accounts"]
                headers = self._get_headers(ws)
                email_col  = self._col_index(headers, "email")
                status_col = self._col_index(headers, "status")
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if str(row[email_col] or "").strip() == email:
                        wb.close()
                        return str(row[status_col] or "").strip()
                wb.close()
                return ""
            except Exception as e:
                log.error(f"❌ Lỗi đọc account status: {e}")
                return ""

    # ──────────────────────────────────────────────────────────────────────────
    # Public: Proxies sheet
    # ──────────────────────────────────────────────────────────────────────────

    def get_active_proxies(self) -> list:
        """Đọc danh sách proxy active từ sheet Proxies. Trả về list[str]."""
        with self._lock:
            try:
                wb = openpyxl.load_workbook(str(self.xlsx_path), read_only=True)
                if "Proxies" not in wb.sheetnames:
                    wb.close()
                    return []
                ws = wb["Proxies"]
                headers = self._get_headers(ws)
                proxy_col  = self._col_index(headers, "proxy")
                status_col = self._col_index(headers, "status") if "status" in headers else None

                results = []
                for row in ws.iter_rows(min_row=2, values_only=True):
                    proxy = str(row[proxy_col] or "").strip()
                    if not proxy:
                        continue
                    if status_col is not None:
                        status = str(row[status_col] or "").strip().lower()
                        if status in ("disabled", "inactive", "0"):
                            continue
                    results.append(proxy)
                wb.close()
                log.info(f"🔌 Đọc được {len(results)} proxy active từ XLSX.")
                return results
            except Exception as e:
                log.error(f"❌ Lỗi đọc proxies: {e}")
                return []

    def load_permanent_counts(self, proxy_pool):
        """
        Đếm số SUCCESS theo proxy từ sheet Accounts để khôi phục trạng thái proxy_pool.
        """
        with self._lock:
            try:
                wb = openpyxl.load_workbook(str(self.xlsx_path), read_only=True)
                ws = wb["Accounts"]
                headers = self._get_headers(ws)
                proxy_col  = self._col_index(headers, "proxy_used")
                status_col = self._col_index(headers, "status")

                counts: dict = {}
                for row in ws.iter_rows(min_row=2, values_only=True):
                    status = str(row[status_col] or "").strip()
                    if status == "SUCCESS":
                        proxy = str(row[proxy_col] or "").strip()
                        if proxy:
                            counts[proxy] = counts.get(proxy, 0) + 1
                wb.close()

                for proxy_str, count in counts.items():
                    if hasattr(proxy_pool, "set_permanent_count"):
                        proxy_pool.set_permanent_count(proxy_str, count)
                log.info(f"📊 Khôi phục permanent count cho {len(counts)} proxy từ XLSX.")
            except Exception as e:
                log.warning(f"⚠️ Không thể load permanent counts: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Static: tạo file mẫu
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def create_template(xlsx_path: str) -> bool:
        """Tạo file XLSX mẫu với 3 sheet: Mails, Accounts, Proxies."""
        try:
            wb = Workbook()

            # Sheet Mails
            ws_mails = wb.active
            ws_mails.title = "Mails"
            XlsxConnection._write_header(ws_mails, MAILS_HEADERS, color="4472C4")
            ws_mails.append(["example@gmail.com", "emailpassword", "1995-06-15", "東京都", "", "PENDING"])
            for col, w in zip("ABCDEF", [35, 20, 14, 16, 20, 14]):
                ws_mails.column_dimensions[col].width = w

            # Sheet Accounts
            ws_accounts = wb.create_sheet("Accounts")
            XlsxConnection._write_header(ws_accounts, ACCOUNTS_HEADERS, color="70AD47")
            for i, w in enumerate([35, 18, 18, 20, 16, 18, 30, 12, 20, 40], 1):
                ws_accounts.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

            # Sheet Proxies
            ws_proxies = wb.create_sheet("Proxies")
            XlsxConnection._write_header(ws_proxies, PROXIES_HEADERS, color="ED7D31")
            ws_proxies.append(["http://host:port:user:pass", "active"])
            ws_proxies.column_dimensions["A"].width = 40
            ws_proxies.column_dimensions["B"].width = 12

            wb.save(str(xlsx_path))
            wb.close()
            log.info(f"✅ Đã tạo file XLSX mẫu tại: {xlsx_path}")
            return True
        except Exception as e:
            log.error(f"❌ Lỗi tạo file XLSX mẫu: {e}")
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _ensure_sheets(self, wb: Workbook):
        """Tạo các sheet còn thiếu trong file XLSX."""
        if "Mails" not in wb.sheetnames:
            ws = wb.create_sheet("Mails")
            self._write_header(ws, MAILS_HEADERS, color="4472C4")
        if "Accounts" not in wb.sheetnames:
            ws = wb.create_sheet("Accounts")
            self._write_header(ws, ACCOUNTS_HEADERS, color="70AD47")
        if "Proxies" not in wb.sheetnames:
            ws = wb.create_sheet("Proxies")
            self._write_header(ws, PROXIES_HEADERS, color="ED7D31")

    @staticmethod
    def _write_header(ws, headers: list, color: str = "4472C4"):
        ws.append(headers)
        for cell in ws[1]:
            cell.font  = Font(bold=True, color="FFFFFF")
            cell.fill  = PatternFill("solid", fgColor=color)
            cell.alignment = Alignment(horizontal="center")

    @staticmethod
    def _get_headers(ws) -> list:
        return [str(cell.value or "").strip().lower() for cell in next(ws.iter_rows(min_row=1, max_row=1))]

    @staticmethod
    def _col_index(headers: list, col_name: str) -> int:
        col_name = col_name.lower()
        try:
            return headers.index(col_name)
        except ValueError:
            raise KeyError(f"Không tìm thấy cột '{col_name}'. Headers: {headers}")
