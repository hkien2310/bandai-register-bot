# 🎮 Sơ Đồ Luồng Đăng Ký Namco Parks Auto Bot

## Tổng Quan Luồng Chính

```mermaid
flowchart TD
    START["🚀 Bắt đầu<br/>(main.py)"] --> READ_EMAIL["📧 Đọc danh sách email<br/>từ emails.txt"]
    READ_EMAIL --> SYNC_CSV["📝 Đồng bộ vào accounts.csv<br/>(Thêm mới = PENDING)"]
    SYNC_CSV --> QUEUE["📦 Đưa email PENDING/FAILED<br/>vào hàng đợi (Queue)"]
    QUEUE --> WORKER["👷 Worker nhận email từ Queue"]
    
    WORKER --> S1["🌐 Bước 1: Vào Trang Chủ"]
    S1 --> S2["🔗 Bước 2: Click Get BNID"]
    S2 --> S3["📋 Bước 3: Đăng Ký BNID<br/>(Email + OTP)"]
    S3 --> S4["📝 Bước 4: Điền Profile<br/>Namco Parks"]
    S4 --> S5["📱 Bước 5: Xác Thực SMS"]
    S5 --> SUCCESS["✅ SUCCESS<br/>Ghi CSV + Sync Sheet"]
    
    SUCCESS --> CHECK_QUEUE{{"Còn email<br/>trong Queue?"}}
    CHECK_QUEUE -->|Có| WORKER
    CHECK_QUEUE -->|Hết| RETRY{{"Có email FAILED?"}}
    RETRY -->|Có| QUEUE
    RETRY -->|Không| SHEETS["🌐 Đồng bộ Google Sheets"]
    SHEETS --> END["🎉 Hoàn tất"]

    style START fill:#4CAF50,color:#fff
    style SUCCESS fill:#4CAF50,color:#fff
    style END fill:#2196F3,color:#fff
    style S1 fill:#FF9800,color:#fff
    style S2 fill:#FF9800,color:#fff
    style S3 fill:#E91E63,color:#fff
    style S4 fill:#9C27B0,color:#fff
    style S5 fill:#9C27B0,color:#fff
```

---

## Bước 1: Vào Trang Chủ Namco Parks

```mermaid
flowchart TD
    S1_START["🌐 Bước 1"] --> OPEN["Mở trình duyệt<br/>(Chromium + Proxy)"]
    OPEN --> GOTO["Truy cập trang chủ<br/>parks2.bandainamco-am.co.jp"]
    GOTO --> WAIT["Chờ tải trang<br/>(3-5 giây ngẫu nhiên)"]
    WAIT --> FIND_LINK{{"Tìm link<br/>新規会員登録?"}}
    FIND_LINK -->|Tìm thấy| CLICK["Click link đăng ký"]
    FIND_LINK -->|Không thấy| ERR1["❌ Lỗi Bước 1<br/>Vào trang chủ thất bại<br/>(Proxy chết / Web sập)"]
    CLICK --> S1_DONE["✅ Checkpoint: Step 1 Done"]

    style S1_START fill:#FF9800,color:#fff
    style S1_DONE fill:#4CAF50,color:#fff
    style ERR1 fill:#F44336,color:#fff
```

---

## Bước 2: Click Nút Get BNID

```mermaid
flowchart TD
    S2_START["🔗 Bước 2"] --> COOKIE{{"Có Cookie Banner?"}}
    COOKIE -->|Có| ACCEPT["Bấm OK để tắt banner"]
    COOKIE -->|Không| FIND_BTN
    ACCEPT --> FIND_BTN{{"Tìm nút vàng<br/>バンダイナムコIDを取得?"}}
    FIND_BTN -->|Tìm thấy| CLICK_BTN["Click nút Get BNID"]
    FIND_BTN -->|Không thấy| ERR2["❌ Lỗi Bước 2<br/>Click nút Get BNID thất bại"]
    CLICK_BTN --> REDIRECT["Chuyển hướng sang<br/>account.bandainamcoid.com"]
    REDIRECT --> S2_DONE["✅ Checkpoint: Step 2 Done"]

    style S2_START fill:#FF9800,color:#fff
    style S2_DONE fill:#4CAF50,color:#fff
    style ERR2 fill:#F44336,color:#fff
```

---

## Bước 3: Đăng Ký BNID + OTP Email (Quan trọng nhất)

```mermaid
flowchart TD
    S3_START["📋 Bước 3"] --> FILL["Điền Email + Password<br/>(có human delay)"]
    FILL --> TICK1["Tick tất cả checkbox<br/>điều khoản"]
    TICK1 --> SUBMIT1["Bấm nút Đăng Ký"]
    SUBMIT1 --> CHECK_RESP{{"Hệ thống<br/>phản hồi gì?"}}
    
    CHECK_RESP -->|"Giao diện<br/>Quốc gia/Ngày sinh"| FILL_DOB["Chọn JP + Điền ngày sinh"]
    CHECK_RESP -->|"Email đã tồn tại"| LOGIN["Chuyển sang luồng Login<br/>(Dùng email/pass đã có)"]
    CHECK_RESP -->|"Timeout"| ERR3A["❌ Lỗi Bước 3<br/>Mạng chậm hoặc web thay đổi"]
    
    FILL_DOB --> TICK2["Tick checkbox bổ sung"]
    TICK2 --> SUBMIT2["Bấm nút Đồng ý"]
    SUBMIT2 --> WAIT_OTP["⏳ Chờ OTP Email<br/>(Poll Gmail IMAP 120s)<br/>Quét cả Inbox + Spam"]
    
    WAIT_OTP --> OTP_FOUND{{"Nhận được OTP?"}}
    OTP_FOUND -->|Có| FILL_OTP["Điền mã OTP 6 số"]
    OTP_FOUND -->|Không| ERR3B["❌ Lỗi Bước 3<br/>Không nhận được OTP sau 120s"]
    
    FILL_OTP --> SUBMIT_OTP["Bấm Submit OTP"]
    SUBMIT_OTP --> SCAN_LOOP["🔄 Vòng lặp càn quét<br/>(Tối đa 4 màn hình)"]
    
    SCAN_LOOP --> SCAN_TEXT["Lấy toàn bộ text<br/>trên màn hình"]
    SCAN_TEXT --> REGEX{{"Regex tìm thấy<br/>mã B + 12 số?"}}
    REGEX -->|Có| SAVE_BNID["🎯 Lưu BNID User Code"]
    REGEX -->|Không| FIND_NEXT{{"Có nút<br/>Agree/Continue/OK?"}}
    
    SAVE_BNID --> FIND_NEXT
    FIND_NEXT -->|Có| CLICK_NEXT["Bấm nút đi tiếp"]
    CLICK_NEXT --> CHECK_URL{{"URL chuyển về<br/>Namco Parks?"}}
    CHECK_URL -->|Chưa| SCAN_TEXT
    CHECK_URL -->|Rồi| S3_DONE
    FIND_NEXT -->|Không| S3_DONE["✅ Checkpoint: Step 3 Done<br/>+ BNID User Code"]

    LOGIN --> S3_DONE

    style S3_START fill:#E91E63,color:#fff
    style S3_DONE fill:#4CAF50,color:#fff
    style SAVE_BNID fill:#FF9800,color:#fff
    style SCAN_LOOP fill:#2196F3,color:#fff
    style ERR3A fill:#F44336,color:#fff
    style ERR3B fill:#F44336,color:#fff
```

---

## Bước 4: Điền Profile Namco Parks + Thuê Số Điện Thoại

```mermaid
flowchart TD
    S4_START["📝 Bước 4"] --> RENT_PHONE["📱 Thuê số ĐT Nhật<br/>(API Viotp)"]
    RENT_PHONE --> RENT_OK{{"Thuê thành công?"}}
    RENT_OK -->|Có| FILL_FORM["Điền Nickname + SĐT<br/>vào form Namco Parks"]
    RENT_OK -->|Không| RETRY_RENT{{"Thử lại<br/>(Tối đa 3 lần)"}}
    RETRY_RENT -->|Còn lượt| RENT_PHONE
    RETRY_RENT -->|Hết lượt| ERR4A["❌ Lỗi Bước 4<br/>API hết số hoặc bị lỗi"]
    
    FILL_FORM --> SUBMIT_FORM["Bấm 登録する"]
    SUBMIT_FORM --> CHECK_SMS{{"Chuyển sang<br/>trang SMS OTP?"}}
    CHECK_SMS -->|Có| S4_DONE["✅ Checkpoint: Step 4 Done"]
    CHECK_SMS -->|"Đã đăng ký rồi"| ALREADY["✅ SUCCESS<br/>(Đã liên kết từ trước)"]
    CHECK_SMS -->|Lỗi| ERR4B["❌ Lỗi Bước 4<br/>Điền Profile thất bại"]

    style S4_START fill:#9C27B0,color:#fff
    style S4_DONE fill:#4CAF50,color:#fff
    style ALREADY fill:#4CAF50,color:#fff
    style ERR4A fill:#F44336,color:#fff
    style ERR4B fill:#F44336,color:#fff
```

---

## Bước 5: Xác Thực SMS OTP

```mermaid
flowchart TD
    S5_START["📱 Bước 5"] --> POLL_SMS["⏳ Poll OTP từ API Viotp<br/>(Chờ tối đa 120s)"]
    POLL_SMS --> SMS_FOUND{{"Nhận được<br/>mã SMS?"}}
    SMS_FOUND -->|Có| FILL_SMS["Điền mã SMS 6 số"]
    SMS_FOUND -->|Không| ERR5["❌ Lỗi Bước 5<br/>Không nhận được SMS OTP"]
    
    FILL_SMS --> SUBMIT_SMS["Bấm 認証する"]
    SUBMIT_SMS --> VERIFY{{"Về trang chủ<br/>top.html?"}}
    VERIFY -->|Có| S5_DONE["✅ Checkpoint: Step 5 Done<br/>🎉 ĐĂNG KÝ THÀNH CÔNG!"]
    VERIFY -->|Không| ERR5B["❌ Lỗi Bước 5<br/>Xác thực SMS thất bại"]

    style S5_START fill:#9C27B0,color:#fff
    style S5_DONE fill:#4CAF50,color:#fff
    style ERR5 fill:#F44336,color:#fff
    style ERR5B fill:#F44336,color:#fff
```

---

## Bảng Tóm Tắt Các Loại Lỗi

| Bước | Mã Lỗi | Nguyên Nhân | Khách Tự Khắc Phục |
|------|---------|-------------|---------------------|
| 1 | `Lỗi Bước 1 (Vào trang chủ)` | Proxy chết / Web sập / Mạng yếu | Đổi proxy hoặc kiểm tra mạng |
| 2 | `Lỗi Bước 2 (Click nút Get BNID)` | Web thay đổi giao diện | Liên hệ hỗ trợ |
| 3 | `Lỗi Bước 3 (OTP Email)` | Bandai không gửi OTP / Gmail chặn | Kiểm tra hòm thư Spam |
| 3 | `Lỗi Bước 3 (Tạo BNID): Email đã được sử dụng` | Email đã đăng ký trước đó | Dùng email khác |
| 4 | `Lỗi Bước 4 (Thuê số SMS)` | API Viotp hết số hoặc hết tiền | Nạp tiền API hoặc chờ |
| 4 | `Lỗi Bước 4 (Điền Profile)` | Web timeout / Proxy lag | Đổi proxy, chạy lại |
| 5 | `Lỗi Bước 5 (Xác thực SMS)` | Số ảo không nhận được SMS | Chạy lại để đổi số mới |

---

## Cấu Trúc Thư Mục Giao Cho Khách

```
📦 Namco_Bot_v1.0/
┣ 📜 RUN_BOT.bat          ← Khách click đúp để chạy
┣ 📜 .env                 ← Cấu hình API key, webhook
┣ 📂 data/
┃ ┣ 📜 emails.txt         ← Khách bỏ email vào đây
┃ ┣ 📜 proxies.txt        ← Khách bỏ proxy vào đây
┃ ┣ 📜 accounts.csv       ← Kết quả xuất ra đây
┃ ┗ 📜 run.log            ← Log chi tiết để debug
┣ 📂 src/                 ← Mã nguồn (đóng gói thì ẩn)
┗ 📂 .venv/               ← Môi trường Python
```
