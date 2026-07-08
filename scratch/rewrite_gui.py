import re

with open("gui.py", "r", encoding="utf-8") as f:
    content = f.read()

# Thay thế logic khởi tạo UI
new_setup_ui = """    def setup_ui(self):
        # Tabs container
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.tab_register = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.tab_register, text="Đăng ký tài khoản")
        
        self.tab_purchase = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.tab_purchase, text="Auto Purchase")

        # --- TAB 1: Đăng Ký ---
        frame = self.tab_register
        
        ttk.Label(frame, text="Đường dẫn Browser (trống = mặc định):").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.browser_path_var, width=45).grid(row=0, column=1, sticky=tk.W, pady=5)
        ttk.Button(frame, text="Chọn", command=self.choose_browser).grid(row=0, column=2, padx=5)

        ttk.Label(frame, text="Số lượng chạy (0 = Tất cả):").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.limit_var, width=15).grid(row=1, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="Số Worker (chạy song song):").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.workers_var, width=15).grid(row=2, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="Ngày sinh mặc định (YYYY-MM-DD):").grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.default_dob_var, width=15).grid(row=3, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="Tỉnh/Thành phố mặc định:").grid(row=4, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.default_pref_var, width=15).grid(row=4, column=1, sticky=tk.W, pady=5)

        chk_frame = ttk.Frame(frame)
        chk_frame.grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=10)
        ttk.Checkbutton(chk_frame, text="Chạy ngầm (Headless)", variable=self.headless_var).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(chk_frame, text="Dùng Proxy", variable=self.proxy_var).pack(side=tk.LEFT, padx=10)

        sheet_frame = ttk.Frame(frame)
        sheet_frame.grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=(0, 5))
        ttk.Label(sheet_frame, text="📊 Google Sheet:").pack(side=tk.LEFT)
        self.sheet_link = tk.Label(
            sheet_frame, text="(chưa cấu hình)", fg="#1a73e8", cursor="hand2", font=("Arial", 10, "underline")
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

        # --- TAB 2: Auto Purchase ---
        p_frame = self.tab_purchase
        
        ttk.Label(p_frame, text="Link Sản Phẩm:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.product_link_var = tk.StringVar()
        ttk.Entry(p_frame, textvariable=self.product_link_var, width=45).grid(row=0, column=1, sticky=tk.W, pady=5)
        self.fetch_btn = ttk.Button(p_frame, text="Fetch", command=self.fetch_options)
        self.fetch_btn.grid(row=0, column=2, padx=5)
        
        ttk.Label(p_frame, text="Option Phân Loại:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.option_var = tk.StringVar()
        self.option_cb = ttk.Combobox(p_frame, textvariable=self.option_var, width=43, state="readonly")
        self.option_cb.grid(row=1, column=1, columnspan=2, sticky=tk.W, pady=5)
        
        ttk.Label(p_frame, text="Số lượng Account (X):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.purchase_count_var = tk.StringVar()
        self.purchase_count_var.set("5")
        ttk.Entry(p_frame, textvariable=self.purchase_count_var, width=15).grid(row=2, column=1, sticky=tk.W, pady=5)
        
        p_btn_frame = ttk.Frame(p_frame)
        p_btn_frame.grid(row=3, column=0, columnspan=3, pady=15)
        
        self.start_purchase_btn = ttk.Button(p_btn_frame, text="🛒 BẮT ĐẦU MUA", command=self.start_purchase, width=20)
        self.start_purchase_btn.pack(side=tk.LEFT, padx=5)

        # --- LOG FRAME CHUNG (Bên ngoài Notebook) ---
        log_label_frame = ttk.Frame(self.root, padding="0 5 0 0")
        log_label_frame.pack(fill=tk.X, padx=10)
        ttk.Label(log_label_frame, text="Tiến trình đang chạy:").pack(side=tk.LEFT)
        self.copy_btn = ttk.Button(log_label_frame, text="📋 Sao chép Log", command=self.copy_log)
        self.copy_btn.pack(side=tk.RIGHT)

        self.log_listbox = tk.Listbox(self.root, height=10, bg="#f0f0f0", fg="#333", font=("Arial", 11))
        self.log_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

    def fetch_options(self):
        link = self.product_link_var.get().strip()
        if not link:
            messagebox.showwarning("Lỗi", "Vui lòng nhập link sản phẩm!")
            return
            
        self.fetch_btn.config(state=tk.DISABLED, text="Đang lấy...")
        self.log_listbox.insert(tk.END, "🔄 Đang fetch dữ liệu option từ link...")
        self.log_listbox.see(tk.END)
        
        def _do_fetch():
            import src.flows.auto_purchase as ap
            options = ap.fetch_product_options(link)
            
            def _update_ui():
                self.fetch_btn.config(state=tk.NORMAL, text="Fetch")
                if options:
                    display_list = [f"{opt['label']} (ID: {opt['id']})" for opt in options]
                    self.option_cb['values'] = display_list
                    if display_list:
                        self.option_cb.current(0)
                    self.log_listbox.insert(tk.END, f"✅ Đã tải thành công {len(options)} options.")
                else:
                    self.option_cb['values'] = []
                    self.option_cb.set("")
                    self.log_listbox.insert(tk.END, "⚠️ Không tìm thấy option nào (hoặc link sai).")
                self.log_listbox.see(tk.END)
                
            self.root.after(0, _update_ui)
            
        threading.Thread(target=_do_fetch, daemon=True).start()

    def start_purchase(self):
        link = self.product_link_var.get().strip()
        opt_text = self.option_var.get()
        count_str = self.purchase_count_var.get().strip()
        
        if not link or not opt_text:
            messagebox.showwarning("Lỗi", "Vui lòng nhập link và fetch option trước!")
            return
            
        try:
            count = int(count_str)
            if count <= 0: raise ValueError
        except:
            messagebox.showwarning("Lỗi", "Số lượng tài khoản phải là số lớn hơn 0!")
            return
            
        # Parse option ID from selected text: Label (ID: 123)
        opt_id = ""
        import re
        m = re.search(r"\(ID: (.*?)\)$", opt_text)
        if m:
            opt_id = m.group(1)
            
        self.log_listbox.insert(tk.END, f"🚀 Bắt đầu giả lập mua hàng: {count} accounts. Option: {opt_id}")
        self.log_listbox.see(tk.END)
        
        def _do_purchase():
            from src.utils.google_sheets_manager import GoogleSheetsManager
            from src.utils.logger import get_logger
            log = get_logger("purchase_task")
            
            log.info("Đang kiểm tra Google Sheets và lọc tài khoản...")
            sm = GoogleSheetsManager()
            eligible_accs = sm.get_accounts_for_purchase(link, count)
            
            if not eligible_accs:
                log.info("⚠️ Không tìm thấy tài khoản nào đủ điều kiện hoặc chưa mua link này!")
                return
                
            log.info(f"🎉 Đã chọn {len(eligible_accs)} tài khoản để mua hàng:")
            for a in eligible_accs:
                log.info(f"   - {a['email']} (Hàng {a['row_index']})")
                
            log.info("🚧 Tạm dừng giả lập ở đây theo yêu cầu của user. (Trao đổi luồng mua sau)")
            
            # Ghi chú: Logic Playwright Automation sẽ đưa vào đây sau.
            # Sau khi mua xong thì sẽ gọi: sm.update_purchased_link(a['email'], link)
            
        threading.Thread(target=_do_purchase, daemon=True).start()"""

pattern = r"    def setup_ui\(self\):.*?        frame.rowconfigure\(9, weight=1\)"
content = re.sub(pattern, new_setup_ui, content, flags=re.DOTALL)

with open("gui.py", "w", encoding="utf-8") as f:
    f.write(content)

