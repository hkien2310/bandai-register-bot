import os
os.environ["CONFIG_FILE"] = "config.json"
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import json
import threading
import sys
import queue
import re
import webbrowser
from pathlib import Path

# Thêm root path để import đúng
if getattr(sys, 'frozen', False):
    _exe_dir = Path(sys.executable).parent
    # macOS .app bundle: executable ở NamcoBot.app/Contents/MacOS/NamcoBot
    if _exe_dir.name == "MacOS" and _exe_dir.parent.name == "Contents":
        ROOT_DIR = _exe_dir.parent.parent.parent
    else:
        ROOT_DIR = _exe_dir
else:
    ROOT_DIR = Path(__file__).parent

sys.path.insert(0, str(ROOT_DIR))

config_path = ROOT_DIR / "config.json"

def load_json_config():
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_json_config(data):
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)



def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

class TextRedirector(object):
    def __init__(self, log_queue):
        self.log_queue = log_queue

    def write(self, string):
        self.log_queue.put(strip_ansi(string))

    def flush(self):
        pass

class NamcoBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Namco Parks Auto Bot")
        self.root.geometry("640x480")
        self.root.minsize(700, 500)

        cfg = load_json_config()
        self.limit_var = tk.StringVar()
        self.limit_var.set("")

        self.workers_var = tk.StringVar()
        self.workers_var.set(str(cfg.get("worker_count", 3)))

        self.headless_var = tk.BooleanVar()
        self.headless_var.set(bool(cfg.get("headless", True)))

        self.proxy_var = tk.BooleanVar()
        self.proxy_var.set(bool(cfg.get("use_proxy", True)))

        self.browser_path_var = tk.StringVar()
        self.browser_path_var.set(cfg.get("browser_path", ""))

        self.default_dob_var = tk.StringVar()
        self.default_dob_var.set(cfg.get("default_dob", "1994-05-08"))

        self.default_pref_var = tk.StringVar()
        self.default_pref_var.set(cfg.get("default_prefecture", "愛知県"))

        # Tự động lưu cấu hình khi đóng cửa sổ app
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.setup_ui()

        self.log_queue = queue.Queue()
        self.update_logs()

        # Override stdout/stderr để logger in ra GUI
        sys.stdout = TextRedirector(self.log_queue)
        sys.stderr = TextRedirector(self.log_queue)

    def setup_ui(self):
        frame = ttk.Frame(self.root, padding="15")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Đường dẫn Browser (để trống = dùng mặc định):").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.browser_path_var, width=55).grid(row=0, column=1, sticky=tk.W, pady=5)
        ttk.Button(frame, text="Chọn", command=self.choose_browser).grid(row=0, column=2, padx=5)

        ttk.Label(frame, text="Số lượng chạy (0 hoặc bỏ trống = Chạy tất cả):").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.limit_var, width=15).grid(row=1, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="Số Worker (Luồng chạy song song):").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.workers_var, width=15).grid(row=2, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="Ngày sinh mặc định (YYYY-MM-DD):").grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.default_dob_var, width=15).grid(row=3, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="Tỉnh/Thành phố mặc định:").grid(row=4, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.default_pref_var, width=15).grid(row=4, column=1, sticky=tk.W, pady=5)

        chk_frame = ttk.Frame(frame)
        chk_frame.grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=10)
        ttk.Checkbutton(chk_frame, text="Chạy ngầm (Headless)", variable=self.headless_var).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(chk_frame, text="Dùng Proxy", variable=self.proxy_var).pack(side=tk.LEFT, padx=10)

        # Link Google Sheet
        sheet_frame = ttk.Frame(frame)
        sheet_frame.grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=(0, 5))
        ttk.Label(sheet_frame, text="📊 Google Sheet:").pack(side=tk.LEFT)
        self.sheet_link = tk.Label(
            sheet_frame,
            text="(chưa cấu hình)",
            fg="#1a73e8",
            cursor="hand2",
            font=("Arial", 10, "underline")
        )
        self.sheet_link.pack(side=tk.LEFT, padx=5)
        self.sheet_link.bind("<Button-1>", self.open_sheet_link)
        self._update_sheet_link()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=7, column=0, columnspan=3, pady=10)

        self.start_btn = ttk.Button(btn_frame, text="🚀 BẮT ĐẦU CHẠY", command=self.start_bot, width=20)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="🛑 DỪNG LẠI", command=self.stop_bot, width=20, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        log_label_frame = ttk.Frame(frame)
        log_label_frame.grid(row=8, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(log_label_frame, text="Tiến trình đang chạy:").pack(side=tk.LEFT)
        self.copy_btn = ttk.Button(log_label_frame, text="📋 Sao chép Log", command=self.copy_log)
        self.copy_btn.pack(side=tk.RIGHT)

        self.log_listbox = tk.Listbox(frame, height=10, bg="#f0f0f0", fg="#333", font=("Arial", 11))
        self.log_listbox.grid(row=9, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S))

        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(9, weight=1)

    def choose_browser(self):
        path = filedialog.askopenfilename(title="Chọn file chạy trình duyệt (Chromium/Chrome)")
        if path:
            self.browser_path_var.set(path)

    def _update_sheet_link(self):
        """Cập nhật text link sheet dựa trên biến ẩn trong code."""
        import src.config as app_config
        sheet_id = app_config.GOOGLE_SHEET_ID.strip()
        if sheet_id and sheet_id != "PASTE_YOUR_GOOGLE_SHEET_ID_HERE":
            self._sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
            self.sheet_link.config(text="Mở Google Sheet ↗", fg="#1a73e8", cursor="hand2")
        else:
            self._sheet_url = ""
            self.sheet_link.config(text="(chưa cấu hình Sheet ID)", fg="#999")

    def open_sheet_link(self, event=None):
        if self._sheet_url:
            webbrowser.open(self._sheet_url)

    def update_logs(self):
        user_keywords = [
            "🚀 Bắt đầu xử lý:",
            "✅", "❌", "⚠️", "🔄", "⏳", "🎉", "🛑", "🔥", "🚧",
            "proxy", "[ERROR]", "[WARNING]",
            "Không còn", "kết nối", "Sheets", "SMS",
            "HOÀN TẤT", "BẮT ĐẦU", "GIỚI HẠN",
            "Loaded", "balance", "Hoàn thành mẻ", "Step",
            "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10."
        ]

        while not self.log_queue.empty():
            raw_msg = self.log_queue.get()
            msg = raw_msg.strip()
            if not msg:
                continue

            raw_lower = msg.lower()
            if "—" in msg:
                display_msg = msg.split("—", 1)[1].strip()
            else:
                display_msg = msg

            check_text = raw_lower + " " + display_msg.lower()
            is_user_friendly = any(kw.lower() in check_text for kw in user_keywords)
            if not is_user_friendly:
                continue

            self.log_listbox.insert(tk.END, "• " + display_msg)

            if self.log_listbox.size() > 30:
                self.log_listbox.delete(0)

            self.log_listbox.see(tk.END)
        self.root.after(50, self.update_logs)

    def save_settings(self):
        """Lưu toàn bộ cài đặt vào config.json duy nhất"""
        cfg = load_json_config()
        try:
            cfg["worker_count"] = int(self.workers_var.get())
        except:
            cfg["worker_count"] = 3
        cfg["headless"] = self.headless_var.get()
        cfg["use_proxy"] = self.proxy_var.get()
        cfg["browser_path"] = self.browser_path_var.get()
        cfg["default_dob"] = self.default_dob_var.get()
        cfg["default_prefecture"] = self.default_pref_var.get()
        save_json_config(cfg)

    def start_bot(self):
        # Lưu config trước
        self.save_settings()

        # Import src.config SAU KHI lưu để nó đọc giá trị mới nhất
        import importlib
        import src.config as bot_config
        importlib.reload(bot_config)

        # Reset STOP_FLAG trực tiếp trên module đang chạy
        bot_config.STOP_FLAG = False

        self.start_btn.config(state=tk.DISABLED, text="⏳ ĐANG CHẠY...")
        self.stop_btn.config(state=tk.NORMAL, text="🛑 DỪNG LẠI")
        self.log_listbox.insert(tk.END, "🚀 Đang khởi động tiến trình, vui lòng không tắt...")
        self.log_listbox.see(tk.END)

        limit_val = self.limit_var.get().strip()
        limit = int(limit_val) if limit_val and limit_val.isdigit() else 0

        threading.Thread(target=self.run_bot_thread, args=(limit,), daemon=True).start()

    def stop_bot(self):
        """Gửi lệnh dừng cho bot — set STOP_FLAG trực tiếp trên module đang chạy."""
        self.stop_btn.config(state=tk.DISABLED, text="⏳ ĐANG DỪNG...")
        self.log_listbox.insert(tk.END, "🛑 Đang cưỡng chế dừng tất cả tiến trình và đóng trình duyệt...")
        self.log_listbox.see(tk.END)

        # Import trực tiếp module đang chạy và set flag — KHÔNG reload
        import src.config as bot_config
        bot_config.STOP_FLAG = True

        # Kill trực tiếp các tiến trình Chrome/Chromium của bot ở cấp độ OS (Thread-safe & Tức thời)
        import subprocess
        import sys
        
        def kill_os_processes():
            try:
                if sys.platform == "win32":
                    # Lệnh Windows
                    subprocess.run('wmic process where "commandline like \'%namco_browser_worker%\'" call terminate', shell=True, capture_output=True)
                else:
                    # Lệnh macOS/Linux
                    subprocess.run(["pkill", "-9", "-f", "namco_browser_worker"], capture_output=True)
            except Exception:
                pass
            
        threading.Thread(target=kill_os_processes, daemon=True).start()

    def run_bot_thread(self, limit):
        import main
        sys.argv = ["gui.py"]
        if limit > 0:
            sys.argv.extend(["--limit", str(limit)])

        try:
            main.main()
        except SystemExit as e:
            code = e.code
            def update_sysexit(c=code):
                if c and c != 0:
                    self.log_listbox.insert(tk.END, f"❌ Bot thoát với mã lỗi: {c}")
                else:
                    self.log_listbox.insert(tk.END, "✅ Bot đã thoát thành công.")
                self.log_listbox.see(tk.END)
            self.root.after(0, update_sysexit)
        except Exception as e:
            def update_err(err=str(e)):
                self.log_listbox.insert(tk.END, f"❌ Lỗi: {err}")
                self.log_listbox.see(tk.END)
            self.root.after(0, update_err)
        finally:
            def update_done():
                self.start_btn.config(state=tk.NORMAL, text="🚀 BẮT ĐẦU CHẠY")
                self.stop_btn.config(state=tk.DISABLED, text="🛑 DỪNG LẠI")
                self.log_listbox.insert(tk.END, "✅ Trạng thái: Đã hoàn tất công việc!")
                self.log_listbox.see(tk.END)
            self.root.after(0, update_done)

    def copy_log(self):
        """Sao chép toàn bộ log trong listbox vào clipboard."""
        logs = self.log_listbox.get(0, tk.END)
        if logs:
            text = "\n".join(logs)
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            
            # Đổi chữ hiển thị trên nút tạm thời để báo thành công
            orig_text = self.copy_btn.cget("text")
            self.copy_btn.config(text="📋 ĐÃ SAO CHÉP!")
            self.root.after(1500, lambda: self.copy_btn.config(text=orig_text))

    def on_close(self):
        """Lưu cấu hình và thoát app an toàn."""
        try:
            self.save_settings()
        except:
            pass
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = NamcoBotGUI(root)
    root.mainloop()
