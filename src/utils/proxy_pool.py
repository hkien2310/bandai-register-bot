import threading
from pathlib import Path
from src.utils.logger import get_logger
from src import config

log = get_logger("proxy_pool")

class ProxyPool:
    def __init__(self, proxy_list: list):
        self.proxies = []
        self.lock = threading.Lock()
        self.index = 0
        
        # Lưu các proxy index đã hoàn thành đăng ký đủ số accounts tối đa
        self.retired_indices = set()
        # Đánh dấu các proxy đã chết vĩnh viễn
        self.dead_indices = set()
        # Đếm số lần lỗi liên tiếp của toàn hệ thống proxy
        self.consecutive_failures = 0
        # Đếm số lần đã sử dụng cho mỗi proxy index (tính cả thành công lẫn thất bại)
        self.usage_counts = {} 
        # ĐẢM BẢO WORKER KHÔNG DÙNG CHUNG PROXY: Set các proxy index đang bị khóa bởi worker
        self.in_use_indices = set()
        
        self.load_from_list(proxy_list)

    def load_from_list(self, proxy_list: list):
        if not proxy_list:
            log.warning("Danh sách proxy trống. Chạy không dùng proxy.")
            return

        for line in proxy_list:
            parsed = self.parse_proxy_string(line)
            if parsed:
                self.proxies.append(parsed)

        log.info(f"Loaded {len(self.proxies)} proxies vào ProxyPool")

    def load_permanent_counts(self, sheets_manager):
        """Đọc sheet Accounts để đếm số lần proxy đã được dùng (SUCCESS) vĩnh viễn.
        
        Gọi hàm này sau khi khởi tạo ProxyPool để khôi phục lịch sử sử dụng proxy.
        """
        if not sheets_manager or not sheets_manager.is_connected():
            return
        
        try:
            all_values = sheets_manager.accounts_sheet.get_all_values()
            if len(all_values) <= 1:
                return
            
            headers = all_values[0]
            try:
                proxy_idx_col = headers.index("Proxy Used")
                status_idx_col = headers.index("Status")
            except ValueError:
                log.warning("Không tìm thấy cột 'Proxy Used' hoặc 'Status' trong sheet Accounts")
                return
            
            # Đếm số lần mỗi proxy raw string đã dùng cho account SUCCESS
            proxy_success_map = {}
            for row in all_values[1:]:
                if len(row) > max(proxy_idx_col, status_idx_col):
                    proxy_raw = row[proxy_idx_col].strip()
                    status = row[status_idx_col].strip().upper()
                    if proxy_raw and status == "SUCCESS":
                        proxy_success_map[proxy_raw] = proxy_success_map.get(proxy_raw, 0) + 1
            
            # Map proxy raw string về proxy index trong pool
            with self.lock:
                for idx, proxy_dict in enumerate(self.proxies):
                    raw = proxy_dict.get("raw", "")
                    if raw in proxy_success_map:
                        count = proxy_success_map[raw]
                        self.usage_counts[idx] = count
                        log.info(f"   [Proxy Pool] Proxy index {idx} đã có {count} acc SUCCESS trước đó (vĩnh viễn).")
                        if count >= config.MAX_ACCOUNTS_PER_PROXY:
                            self.retired_indices.add(idx)
                            log.warning(f"   [Proxy Pool] Retire proxy index {idx} ngay khi khởi động (đã đạt {count}/{config.MAX_ACCOUNTS_PER_PROXY}).")
            
            total_permanent = sum(proxy_success_map.values())
            if total_permanent > 0:
                log.info(f"   [Proxy Pool] Đã khôi phục {total_permanent} lượt sử dụng vĩnh viễn từ Google Sheets.")
                
        except Exception as e:
            log.error(f"Lỗi đọc lịch sử proxy từ Sheets: {e}")

    def parse_proxy_string(self, proxy_str: str) -> dict | None:
        """
        Parse proxy string sang dict chuẩn Playwright.
        """
        try:
            if "@" in proxy_str:
                auth_part, host_part = proxy_str.split("@", 1)
                username, password = auth_part.split(":", 1)
                host, port = host_part.split(":", 1)
                return {
                    "server": f"http://{host}:{port}",
                    "username": username,
                    "password": password,
                    "raw": proxy_str
                }

            parts = proxy_str.split(":")
            if len(parts) == 2:
                return {
                    "server": f"http://{parts[0]}:{parts[1]}",
                    "raw": proxy_str
                }
            elif len(parts) == 4:
                return {
                    "server": f"http://{parts[0]}:{parts[1]}",
                    "username": parts[2],
                    "password": parts[3],
                    "raw": proxy_str
                }
            else:
                log.warning(f"Định dạng proxy không hợp lệ: {proxy_str}")
                return None
        except Exception as e:
            log.error(f"Lỗi parse proxy string '{proxy_str}': {e}")
            return None

    def get_next_proxy(self) -> tuple[dict | None, int | None]:
        """Lấy proxy tiếp theo theo cơ chế Round-robin (thread-safe).
        
        Mỗi lần gọi luôn lấy proxy khác nhau.
        Tự động bỏ qua các proxy đã retired, dead, HOẶC ĐANG ĐƯỢC WORKER KHÁC SỬ DỤNG.
        Proxy được trả về sẽ bị KHÓA (in_use) cho đến khi gọi release_proxy().
        """
        if not self.proxies:
            return None, None
            
        with self.lock:
            if self.consecutive_failures >= 15:
                log.error("❌ Phát hiện 15 proxy liên tiếp chết! Khả năng cao toàn bộ kho proxy hỏng hoặc mất mạng. Tạm dừng cấp proxy!")
                return None, None

            start_index = self.index
            while True:
                curr_idx = self.index
                # Luôn dịch index sang proxy tiếp theo cho các lần gọi sau (đảm bảo đổi proxy liên tục)
                self.index = (self.index + 1) % len(self.proxies)
                
                # BỎ QUA proxy đang bị worker khác dùng, đã retired, hoặc đã chết
                if curr_idx not in self.retired_indices and curr_idx not in self.dead_indices and curr_idx not in self.in_use_indices:
                    proxy = dict(self.proxies[curr_idx])
                    # KHÓA proxy này cho worker hiện tại
                    self.in_use_indices.add(curr_idx)
                    log.info(f"   -> Chọn proxy index={curr_idx} | {proxy.get('server')} (Đã dùng {self.usage_counts.get(curr_idx, 0)}/{config.MAX_ACCOUNTS_PER_PROXY})")
                    return proxy, curr_idx
                
                # Nếu đã duyệt hết 1 vòng mà không tìm được con nào khả dụng
                if self.index == start_index:
                    if len(self.dead_indices) == len(self.proxies):
                        log.error("❌ TẤT CẢ proxy trong kho đều đã chết!")
                        return None, None
                    
                    # Kiểm tra xem tất cả proxy sống đều đang in_use (worker chiếm hết)
                    alive_count = len(self.proxies) - len(self.dead_indices)
                    in_use_alive = len(self.in_use_indices - self.dead_indices)
                    if in_use_alive >= alive_count:
                        return "WAIT", -1
                        
                    log.warning(f"Tất cả proxy sống đều đã đăng ký tối đa {config.MAX_ACCOUNTS_PER_PROXY} acc! Reset giới hạn (không reset proxy chết)...")
                    self.retired_indices.clear()
                    self.usage_counts.clear()
                    # Vòng lặp sẽ tiếp tục tìm proxy sống đầu tiên vừa được un-retire

    def release_proxy(self, proxy_index: int):
        """MỞ KHÓA proxy sau khi worker xử lý xong 1 account (dù thành công hay thất bại).
        
        PHẢI gọi hàm này sau mỗi lần xử lý xong 1 account để worker khác có thể dùng proxy này.
        """
        if proxy_index is None or proxy_index < 0:
            return
        with self.lock:
            self.in_use_indices.discard(proxy_index)

    def mark_used(self, proxy_index: int):
        """Ghi nhận đã sử dụng xong 1 account (dù thành công hay thất bại).
        
        Tăng usage_count và retire nếu đạt giới hạn.
        LƯU Ý: Hàm này KHÔNG tự release proxy. Gọi release_proxy() riêng.
        """
        if proxy_index is None or proxy_index < 0:
            return
        with self.lock:
            self.consecutive_failures = 0  # Reset counter khi proxy chạy hết 1 luồng (sống)
            count = self.usage_counts.get(proxy_index, 0) + 1
            self.usage_counts[proxy_index] = count
            log.info(f"   [Proxy Pool] Proxy index {proxy_index} đã dùng {count}/{config.MAX_ACCOUNTS_PER_PROXY} lần.")
            if count >= config.MAX_ACCOUNTS_PER_PROXY:
                log.warning(f"   [Proxy Pool] Retire proxy index {proxy_index} (Đạt giới hạn tối đa {config.MAX_ACCOUNTS_PER_PROXY} lần sử dụng).")
                self.retired_indices.add(proxy_index)

    def count(self) -> int:
        return len(self.proxies)

    def mark_failed(self, proxy_index: int):
        """Đánh dấu proxy đã chết/lỗi để không sử dụng lại nữa."""
        if proxy_index is None or proxy_index < 0:
            return
        with self.lock:
            self.dead_indices.add(proxy_index)
            self.in_use_indices.discard(proxy_index)  # Mở khóa luôn vì proxy chết rồi
            self.consecutive_failures += 1
            log.warning(f"   [Proxy Pool] Đã loại bỏ vĩnh viễn proxy index {proxy_index} vì bị lỗi kết nối. (Chuỗi chết liên tiếp: {self.consecutive_failures})")
