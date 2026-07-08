import csv
import threading
from pathlib import Path
from datetime import datetime
from src.utils.logger import get_logger

log = get_logger("csv_writer")

class ResultWriter:
    COLUMNS = [
        "email",
        "bandai_password",
        "namco_password",
        "nickname",
        "phone",
        "bnid_user_code",
        "proxy_used",
        "status",
        "created_at",
        "error_details"
    ]

    def __init__(self, output_file: str):
        self.output_file = Path(output_file)
        self.lock = threading.Lock()
        self.init_csv()

    def init_csv(self):
        """Tạo file CSV, viết header hoặc migrate data cũ nếu cấu trúc cột thay đổi."""
        with self.lock:
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            if not self.output_file.exists():
                with open(self.output_file, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(self.COLUMNS)
                log.info(f"Đã khởi tạo file kết quả mới tại {self.output_file}")
                return

            # Nếu file đã tồn tại, đọc để kiểm tra xem có cần migrate không
            rows = []
            try:
                with open(self.output_file, "r", newline="", encoding="utf-8-sig") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        rows.append(row)
            except Exception as e:
                log.warning(f"Không thể đọc file CSV hiện tại để migrate: {e}")
                return

            if not rows:
                return

            # Kiểm tra header và độ dài các dòng
            header = rows[0]
            if header != self.COLUMNS or any(len(row) != len(self.COLUMNS) for row in rows[1:] if row):
                log.info("🔄 Phát hiện cấu trúc CSV cũ hoặc dòng bị lệch. Đang tự động migrate dữ liệu...")
                new_rows = [self.COLUMNS]
                for row in rows[1:]:
                    if not row:
                        continue
                    if len(row) == 11:
                        # Bản cũ có parks_member_id ở cột 6 (index 6)
                        new_row = [
                            row[0],  # email
                            row[1],  # bandai_password
                            row[2],  # namco_password
                            row[3],  # nickname
                            row[4],  # phone
                            row[5],  # bnid_user_code
                            row[7],  # proxy_used
                            row[8],  # status
                            row[9],  # created_at
                            row[10], # error_details
                        ]
                        new_rows.append(new_row)
                    elif len(row) == 10:
                        # Bản cũ hơn 1 tí, tùy xem có namco_password hay không
                        if row[2] == row[1]:
                            new_row = [
                                row[0],  # email
                                row[1],  # bandai_password
                                row[2],  # namco_password
                                row[3],  # nickname
                                row[4],  # phone
                                row[5],  # bnid_user_code
                                row[6],  # proxy_used
                                row[7],  # status
                                row[8],  # created_at
                                row[9],  # error_details
                            ]
                        else:
                            new_row = [
                                row[0],  # email
                                row[1],  # bandai_password
                                row[1],  # namco_password
                                row[2],  # nickname
                                row[3],  # phone
                                row[4],  # bnid_user_code
                                row[6],  # proxy_used
                                row[7],  # status
                                row[8],  # created_at
                                row[9],  # error_details
                            ]
                        new_rows.append(new_row)
                    elif len(row) == len(self.COLUMNS):
                        new_rows.append(row)
                    else:
                        # Điền trống cho đủ cột nếu độ dài khác
                        new_row = row + [""] * (len(self.COLUMNS) - len(row))
                        new_rows.append(new_row[:len(self.COLUMNS)])


                try:
                    with open(self.output_file, "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.writer(f)
                        writer.writerows(new_rows)
                    log.info("✅ Tự động migrate CSV thành công!")
                except Exception as e:
                    log.error(f"Lỗi khi ghi đè file CSV migrated: {e}")


    def _make_row(self, data: dict) -> list:
        """Chuyển dict thành row list theo đúng thứ tự COLUMNS."""
        row = []
        for col in self.COLUMNS:
            row.append(data.get(col, ""))
        # Điền mặc định created_at nếu thành công
        if not data.get("created_at") and data.get("status") == "SUCCESS":
            row[self.COLUMNS.index("created_at")] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return row

    def write(self, data: dict):
        """Upsert 1 dòng vào CSV theo email — update nếu đã tồn tại, insert nếu chưa.
        Thread-safe. Dùng append thay vì rewrite toàn bộ file để nhanh."""
        email = data.get("email", "")
        new_row = self._make_row(data)

        with self.lock:
            # Đọc toàn bộ file
            rows = []
            found = False
            if self.output_file.exists():
                with open(self.output_file, "r", newline="", encoding="utf-8-sig") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        rows.append(row)

            # Tìm dòng có email trùng (cột 0), bỏ qua header
            for i, row in enumerate(rows):
                if i == 0:
                    continue  # header
                if row and row[0] == email:
                    rows[i] = new_row
                    found = True
                    break

            # Nếu không tìm thấy email trùng, thử tìm dòng trống gần nhất (email rỗng hoặc dòng rỗng) để điền vào
            if not found:
                for i, row in enumerate(rows):
                    if i == 0:
                        continue  # header
                    is_empty_row = not row or all(cell.strip() == "" for cell in row) or row[0].strip() == ""
                    if is_empty_row:
                        rows[i] = new_row
                        found = True
                        break

            if not found:
                rows.append(new_row)

            # Ghi lại toàn bộ file
            with open(self.output_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerows(rows)

        log.info(f"📝 {'Cập nhật' if found else 'Thêm mới'} email: {email} → {data.get('status')}")

