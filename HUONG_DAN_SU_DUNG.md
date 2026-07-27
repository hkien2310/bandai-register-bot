# 📖 Hướng dẫn sử dụng Namco Parks Auto Bot

> **Phiên bản:** 1.0 &nbsp;|&nbsp; **Cập nhật:** 2026-07-21  
> **Đối tượng:** Người vận hành bot đăng ký tài khoản Namco Parks tự động

---

## Mục lục

- [1. Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
- [2. Cài đặt & Khởi động lần đầu](#2-cài-đặt--khởi-động-lần-đầu)
- [3. Hướng dẫn chuẩn bị file Excel](#3-hướng-dẫn-chuẩn-bị-file-excel)
  - [3.1 Tạo file mẫu](#31-tạo-file-mẫu)
  - [3.2 Cấu trúc các Sheet](#32-cấu-trúc-các-sheet)
  - [3.3 Bảng tra cứu giá trị STATUS](#33-bảng-tra-cứu-giá-trị-status)
  - [3.4 Cách điền dữ liệu đúng cách](#34-cách-điền-dữ-liệu-đúng-cách)
- [4. Hướng dẫn sử dụng phần mềm (GUI)](#4-hướng-dẫn-sử-dụng-phần-mềm-gui)
  - [4.1 Giao diện tổng thể](#41-giao-diện-tổng-thể)
  - [4.2 Giải thích từng trường cài đặt](#42-giải-thích-từng-trường-cài-đặt)
- [5. Quy trình chạy bot từ A đến Z](#5-quy-trình-chạy-bot-từ-a-đến-z)
- [6. Đọc hiểu kết quả & Log](#6-đọc-hiểu-kết-quả--log)
- [7. Tính năng Tải trước số điện thoại](#7-tính-năng-tải-trước-số-điện-thoại)
- [8. Xử lý lỗi thường gặp](#8-xử-lý-lỗi-thường-gặp)
- [9. Kế hoạch chạy batch lớn](#9-kế-hoạch-chạy-batch-lớn)
- [10. Cấu hình nâng cao (config.json)](#10-cấu-hình-nâng-cao-configjson)
- [Phụ lục A — Danh sách tỉnh Nhật](#phụ-lục-a--danh-sách-tỉnh-nhật)
- [Phụ lục B — FAQ](#phụ-lục-b--faq)

---

## 1. Tổng quan hệ thống

### Bot làm gì?

Bot tự động đăng ký tài khoản **Namco Parks** (`parks2.bandainamco-am.co.jp`) theo trình tự:

```
Email từ file XLSX
       ↓
Mở trình duyệt + Proxy
       ↓
Vào trang Namco Parks → Click "Get BNID"
       ↓
Đăng ký BNID bằng email + OTP Email
       ↓
Điền profile + Thuê số điện thoại Nhật ảo (API SMS)
       ↓
Xác thực SMS OTP
       ↓
✅ Ghi kết quả vào sheet "Accounts" trong file XLSX
```

### Các thành phần cần có

| Thành phần | Mô tả | Bắt buộc |
|---|---|:---:|
| File `.exe` / `.app` | Phần mềm chính (NamcoBot) | ✅ |
| File XLSX | Danh sách email đầu vào + nơi ghi kết quả | ✅ |
| Danh sách Proxy | Proxy IP Nhật để đăng ký | ✅ |
| API SMS key | Thuê số điện thoại Nhật ảo | ✅ |
| Chromium browser | Trình duyệt tự động hóa | ✅ |

---

## 2. Cài đặt & Khởi động lần đầu

### Bước 1 — Giải nén thư mục bot

Sau khi nhận được file, giải nén ra thư mục dễ tìm:

```
📦 NamcoBot/
├── NamcoBot.exe          ← File chạy chính (Windows)
├── NamcoBot.app          ← File chạy chính (macOS)
├── config.json           ← Cấu hình (tự sinh ra sau lần đầu chạy)
└── data/
    └── proxies.txt       ← Danh sách proxy (nếu có sẵn)
```

### Bước 2 — Chạy phần mềm

- **Windows:** Double-click vào `NamcoBot.exe`
- **macOS:** Double-click vào `NamcoBot.app`

> **⚠️ macOS:** Lần đầu chạy có thể bị chặn bởi Gatekeeper. Vào **System Settings → Privacy & Security → Open Anyway** để cho phép.

### Bước 3 — Chọn file trình duyệt

Ở ô **"Đường dẫn Browser"**, bấm nút **\[Chọn\]** và trỏ đến file Chromium:

- Windows: `C:\...\chrome.exe` hoặc `C:\...\chromium.exe`
- macOS: `/Users/.../Chromium.app`

Để trống → bot tự tải Chromium qua Playwright.

---

## 3. Hướng dẫn chuẩn bị file Excel

File Excel là **trung tâm dữ liệu** của toàn bộ hệ thống. Mọi input và output đều nằm trong file này.

---

### 3.1 Tạo file mẫu

Thay vì tự tạo từ đầu, dùng tính năng tích hợp để sinh file đúng chuẩn:

1. Mở phần mềm
2. Bấm nút **\[Tạo file mẫu\]** — nằm bên cạnh ô chọn file XLSX
3. Chọn thư mục lưu → đặt tên `data_bandai.xlsx`
4. Bấm **Save**
5. Phần mềm hiện thông báo thành công và tự điền đường dẫn

---

### 3.2 Cấu trúc các Sheet

File XLSX gồm **5 sheet**, mỗi sheet có chức năng riêng biệt.

---

#### Sheet `Outlooks` — Danh sách email Outlook/Hotmail

Đây là sheet **bạn điền vào nhiều nhất**. Mỗi dòng = 1 tài khoản cần đăng ký.

| Cột | Tên cột | Mô tả | Bắt buộc | Ví dụ |
|:---:|---|---|:---:|---|
| A | `email` | Địa chỉ email Outlook/Hotmail | ✅ | `user123@hotmail.com` |
| B | `email_password` | Mật khẩu email (để bot đọc OTP) | ✅ | `MyPass@2025` |
| C | `dob` | Ngày sinh `YYYY-MM-DD`, trống = dùng mặc định | ❌ | `1990-05-15` |
| D | `prefecture` | Tỉnh/Thành phố Nhật, trống = dùng mặc định | ❌ | `愛知県` |
| E | `nickname` | Biệt danh, trống = dùng mặc định | ❌ | `ヴオン・タイン` |
| F | `status` | Trạng thái xử lý — **KHÔNG TỰ SỬA** | 🔒 | `PENDING` |
| G | `error_details` | Chi tiết lỗi — **KHÔNG TỰ SỬA** | 🔒 | |

**Format đặc biệt — Pipe-separated:**

Thay vì điền nhiều cột, bạn có thể dồn thông tin vào cột A, phân cách bằng dấu `|`:

```
email|password|ms_token|ms_uuid
```

Ví dụ:
```
user123@hotmail.com|MyPass@2025|eyJhbGciOiJSUzI1N...|1234-5678-abcd
```

> 💡 **Mẹo:** Dùng pipe-separated khi export email từ công cụ khác ra dạng 1 cột để dán nhanh, không cần tách ra nhiều cột.

---

#### Sheet `Gmails` — Danh sách email Gmail

| Cột | Tên cột | Mô tả | Bắt buộc |
|:---:|---|---|:---:|
| A | `email` | Địa chỉ Gmail đăng ký | ✅ |
| B | `email_password` | Mật khẩu Gmail | ✅ |
| C | `otp_email` | Email phụ nhận OTP (nếu dùng catch-all) | ❌ |
| D | `otp_pass` | Mật khẩu email phụ | ❌ |
| E | `dob` | Ngày sinh `YYYY-MM-DD` | ❌ |
| F | `prefecture` | Tỉnh/Thành phố Nhật | ❌ |
| G | `nickname` | Biệt danh | ❌ |
| H | `status` | Trạng thái — **KHÔNG TỰ SỬA** | 🔒 |
| I | `error_details` | Chi tiết lỗi — **KHÔNG TỰ SỬA** | 🔒 |

---

#### Sheet `Iclouds` — Danh sách email iCloud

Cấu trúc giống hệt sheet `Gmails`. Dùng khi đăng ký bằng email `@icloud.com`.

---

#### Sheet `Accounts` — Kết quả đăng ký *(OUTPUT)*

> 🚫 **KHÔNG XÓA, KHÔNG SỬA** dữ liệu trong sheet này. Bot tự động ghi và cập nhật. Bạn chỉ mở để đọc kết quả.

| Cột | Tên cột | Mô tả |
|:---:|---|---|
| A | `email` | Email đã đăng ký |
| B | `bandai_password` | Mật khẩu tài khoản Bandai Namco ID |
| C | `namco_password` | Mật khẩu tài khoản Namco Parks |
| D | `nickname` | Biệt danh đã dùng |
| E | `phone` | Số điện thoại ảo đã dùng |
| F | `bnid_user_code` | **Mã BNID quan trọng** — dạng `B` + 12 số |
| G | `proxy_used` | Proxy đã dùng để đăng ký |
| H | `status` | `SUCCESS` / `FAILED` |
| I | `created_at` | Thời điểm hoàn thành |
| J | `error_details` | Lý do thất bại nếu có |

---

#### Sheet `Proxies` — Danh sách Proxy

| Cột | Tên cột | Mô tả | Ví dụ |
|:---:|---|---|---|
| A | `proxy` | Địa chỉ proxy đầy đủ | `http://user:pass@1.2.3.4:8080` |
| B | `status` | Trạng thái proxy | `active` / `dead` |

**Các format proxy hỗ trợ:**

```
http://1.2.3.4:8080
http://username:password@1.2.3.4:8080
socks5://username:password@1.2.3.4:1080
```

---

### 3.3 Bảng tra cứu giá trị STATUS

| Giá trị | Ý nghĩa | Bot sẽ làm gì |
|---|---|---|
| *(trống)* | Chưa xử lý | Đưa vào hàng đợi để chạy |
| `PENDING` | Đang chờ | Đưa vào hàng đợi để chạy |
| `PROCESSING` | Đang chạy | Nếu khởi động lại → tự reset về `PENDING` |
| `SUCCESS` | Thành công | **Bỏ qua**, không chạy lại |
| `FAILED` | Thất bại | Tự động chạy lại ở lần sau |
| `FAIL_NO_RETRY` | Lỗi không thể thử lại | **Bỏ qua vĩnh viễn** (email đã dùng, bị ban...) |
| `HAS_BNID` | Đã có BNID rồi | Chạy lại theo luồng Login thay vì đăng ký mới |

> 💡 **Mẹo:** Muốn chạy lại 1 email cụ thể dù đã `SUCCESS`? Xóa giá trị ở cột `status` của dòng đó (để trống), rồi chạy bot lại.

---

### 3.4 Cách điền dữ liệu đúng cách

**Ví dụ đúng chuẩn — Sheet Outlooks:**

| email | email_password | dob | prefecture | nickname | status |
|---|---|---|---|---|---|
| `user1@hotmail.com` | `Pass123!` | | | | |
| `user2@outlook.com` | `MyPass@456` | `1995-03-20` | `東京都` | `タナカ・ハナコ` | |
| `user3@hotmail.com` | `Secret789` | | | | `PENDING` |

**Lỗi phổ biến khi điền:**

| ❌ Sai | ✅ Đúng |
|---|---|
| Cột email có khoảng trắng: `·user@mail.com·` | `user@mail.com` |
| Ngày sinh sai format: `15/05/1990` | `1990-05-15` (YYYY-MM-DD) |
| Tự gõ status tùy tiện: `done`, `ok`, `xong` | Để trống hoặc dùng đúng: `PENDING` |
| Để Excel đang mở khi chạy bot | Đóng file Excel trước khi bấm Bắt đầu |

---

## 4. Hướng dẫn sử dụng phần mềm (GUI)

### 4.1 Giao diện tổng thể

```
┌──────────────────────────────────────────────────────────────────┐
│  Đường dẫn Browser: [________________________________] [Chọn]    │
│  Số lượng chạy (0 = tất cả): [___]                               │
│  Số Worker (luồng song song): [___]                              │
│  Ngày sinh mặc định: [1990-11-12]                                │
│  Tỉnh/Thành phố mặc định:    [愛知県]                            │
│                                                                    │
│  ☑ Chạy ngầm (Headless)  ☑ Dùng Proxy  ☑ Dùng số lấy trước       │
│  [⬇️ Tải trước số]    [🛑 Dừng tải số]                            │
│  ☑ Dùng list SĐT thủ công [📝 Nhập list SĐT]                     │
│                                                                    │
│  📄 File XLSX: [___________________] [Chọn file] [Tạo file mẫu]  │
│  🗂  Chọn luồng Mail cần chạy: [Outlooks ▼]                      │
│                                                                    │
│           [🚀 BẮT ĐẦU CHẠY]      [🛑 DỪNG LẠI]                  │
│                                                                    │
│  📊 Pending: 45 | Processing: 3 | Success: 12 | Failed: 2        │
│  ────────────────────────────────  [📋 Sao chép Log] [🗑 Xoá Log]│
│  • 🚀 Bắt đầu xử lý: user1@hotmail.com                           │
│  • ✅ user1 — Đăng ký thành công! BNID: B123456789012            │
└──────────────────────────────────────────────────────────────────┘
```

---

### 4.2 Giải thích từng trường cài đặt

#### 🖥 Đường dẫn Browser

Chỉ đến file thực thi của trình duyệt Chromium/Chrome.

- Để trống → bot tự dùng Playwright tải Chromium
- Nên dùng **CloakBrowser** để tránh bị phát hiện là bot
- Bấm `[Chọn]` để duyệt file thay vì gõ tay đường dẫn

---

#### 🔢 Số lượng chạy

Giới hạn số email xử lý trong phiên này.

- `0` hoặc **để trống** = chạy **tất cả** email PENDING
- Nhập số cụ thể (VD: `50`) = chỉ chạy 50 email đầu tiên
- Hữu ích để **test thử** trước khi chạy batch lớn

---

#### 👷 Số Worker (Luồng song song)

Số trình duyệt chạy **đồng thời**, mỗi worker dùng 1 proxy riêng.

- Khuyến nghị: `3–5` cho máy thông thường, `10` cho máy mạnh
- Tăng worker = nhanh hơn nhưng tốn RAM và dễ bị rate-limit hơn

> ⚠️ **Cảnh báo:** Không nên đặt quá **15 workers** cùng lúc. Hệ thống Bandai có giới hạn request và proxy dễ bị đốt.

---

#### 📅 Ngày sinh mặc định

Áp dụng cho các email **không có** cột `dob` riêng trong file XLSX.

- Format bắt buộc: `YYYY-MM-DD` (VD: `1990-11-12`)
- Nên chọn ngày sinh của người trưởng thành (trên 18 tuổi)

---

#### 🗺 Tỉnh/Thành phố mặc định

Tên tỉnh **bằng tiếng Nhật**, áp dụng khi email không có `prefecture` riêng.

- Ví dụ hợp lệ: `愛知県`, `東京都`, `大阪府`
- Xem [Phụ lục A](#phụ-lục-a--danh-sách-tỉnh-nhật) để tra danh sách đầy đủ

---

#### ☑ Chạy ngầm (Headless)

- **Bật ✅** — Trình duyệt chạy ẩn, không hiện cửa sổ. Nhanh hơn, tiết kiệm RAM. **Dùng khi chạy thật.**
- **Tắt ☐** — Trình duyệt hiện lên màn hình. **Dùng khi debug lỗi** để quan sát bot làm gì.

---

#### ☑ Dùng Proxy

- **Bật ✅** — Bot luân phiên dùng proxy từ sheet `Proxies` trong file XLSX.
- **Tắt ☐** — Dùng IP thật của máy. **Không khuyến nghị** khi chạy nhiều tài khoản.

---

#### ☑ Dùng số lấy trước

- **Bật ✅** — Bot lấy số từ kho đã tải sẵn (`data/pre_fetched_numbers.json`). Nhanh hơn.
- **Tắt ☐** — Bot gọi API SMS trực tiếp khi cần (có độ trễ 2–5 giây mỗi lần).

---

#### 📄 File dữ liệu XLSX

Đường dẫn đến file Excel chứa toàn bộ dữ liệu.

- `[Chọn file]` — Duyệt đến file XLSX có sẵn
- `[Tạo file mẫu]` — Tạo file mới đúng chuẩn
- **Bắt buộc phải chọn** trước khi bấm Bắt đầu

---

#### 🗂 Chọn luồng Mail cần chạy

Xác định sheet nào được đọc trong phiên này.

| Lựa chọn | Sheet tương ứng | Loại email |
|---|---|---|
| `Outlooks` | Sheet Outlooks | Hotmail, Outlook.com |
| `Gmails` | Sheet Gmails | Gmail |
| `Iclouds` | Sheet Iclouds | iCloud |

> Bot chỉ chạy **1 sheet tại một thời điểm**.

---

## 5. Quy trình chạy bot từ A đến Z

### Bước 1 — Chuẩn bị file XLSX

1. Mở phần mềm → Bấm `[Tạo file mẫu]` → Lưu tại thư mục dễ tìm
2. Mở file XLSX vừa tạo bằng Excel
3. Vào sheet `Outlooks` (hoặc `Gmails`/`Iclouds` tùy loại email)
4. Điền email + mật khẩu từ **dòng 2** trở đi (dòng 1 là header, không sửa)
5. Vào sheet `Proxies` → Điền danh sách proxy
6. Lưu file (`Ctrl+S`) → **Đóng file Excel lại**

> 🚫 **Quan trọng:** Phải **đóng file Excel** trước khi chạy bot. Nếu file đang mở, bot không thể ghi kết quả và sẽ báo lỗi `Permission denied`.

### Bước 2 — Cấu hình phần mềm

1. Mở phần mềm NamcoBot
2. Bấm `[Chọn file]` → Chọn file XLSX vừa chuẩn bị
3. Chọn đúng sheet ở dropdown (VD: `Outlooks`)
4. Cài **Số lượng chạy**: Để trống = tất cả, hoặc nhập số để test
5. Cài **Số Worker**: Bắt đầu với `3`, tăng dần sau khi quen
6. Điền **Ngày sinh mặc định** hợp lệ
7. Bật **Chạy ngầm** khi chạy thật, bật **Dùng Proxy** nếu đã có proxy

### Bước 3 — Chạy bot

1. Bấm **`[🚀 BẮT ĐẦU CHẠY]`**
2. Bot hiện: `"🚀 Đang khởi động tiến trình, vui lòng không tắt..."`
3. Theo dõi log ở khung phía dưới giao diện
4. Thanh thống kê tự cập nhật mỗi 2 giây

### Bước 4 — Theo dõi tiến trình

```
📊 Session - Pending: 45 | Processing: 3 | Success: 12 | Failed: 2 | NoRetry: 0
```

| Chỉ số | Ý nghĩa |
|---|---|
| **Pending** | Số email còn chờ trong hàng đợi |
| **Processing** | Số email đang được xử lý hiện tại |
| **Success** | Số tài khoản đăng ký thành công trong phiên này |
| **Failed** | Số thất bại — sẽ tự retry khi chạy lại |
| **NoRetry** | Số lỗi vĩnh viễn — không retry nữa |

### Bước 5 — Dừng bot

- **Dừng bình thường:** Đợi bot tự kết thúc — log hiện `"🎉 HOÀN TẤT"`
- **Dừng khẩn cấp:** Bấm `[🛑 DỪNG LẠI]` — đóng tất cả trình duyệt ngay lập tức

> 📌 **Lưu ý:** Nếu dừng giữa chừng, các email đang `PROCESSING` sẽ tự reset về `PENDING` khi khởi động lại. **Không mất dữ liệu.**

### Bước 6 — Kiểm tra kết quả

1. Mở file XLSX
2. Vào sheet **`Accounts`** — xem danh sách tài khoản thành công
3. Vào sheet **`Outlooks`** — xem cột `status` từng email
4. Dùng AutoFilter (`Data → Filter`) để lọc theo `status = SUCCESS`

---

## 6. Đọc hiểu kết quả & Log

### Ký hiệu trong Log

| Ký hiệu | Ý nghĩa |
|:---:|---|
| 🚀 | Bắt đầu xử lý email mới |
| ✅ | Thành công |
| ❌ | Thất bại |
| ⚠️ | Cảnh báo (không nghiêm trọng) |
| 🔄 | Đang retry |
| ⏳ | Đang chờ OTP, SMS... |
| 🎉 | Hoàn tất toàn bộ phiên |
| 🛑 | Đã dừng |

### Các thông báo quan trọng

```
🚀 Bắt đầu xử lý: user@hotmail.com
   → Bot bắt đầu mở trình duyệt xử lý email này

✅ user@hotmail.com — Đăng ký thành công! BNID: B123456789012
   → Thành công, có mã BNID

❌ Lỗi Bước 3 (OTP Email): Không nhận được OTP sau 120s
   → Bot chờ OTP email 120s mà không nhận được

⚠️ SMS API hết số, thử lại sau 15s...
   → Bình thường, bot tự xử lý

🎉 HOÀN TẤT — Tổng Success: 48 / 50
   → Xong toàn bộ phiên
```

### Lọc kết quả trong Excel

Sau khi chạy, mở file XLSX → Sheet **`Accounts`**:

1. Click ô bất kỳ trong hàng header (dòng 1)
2. Vào **Data → Filter** (hoặc `Ctrl+Shift+L`)
3. Click mũi tên ▼ ở cột `status`
4. Chọn `SUCCESS` để xem tài khoản thành công

> 💡 **Mẹo:** Bôi nhiều ô ở cột `status` → nhìn thanh status dưới cùng Excel, sẽ hiện **Count: X**.

---

## 7. Tính năng Tải trước số điện thoại

### Tại sao cần tải trước?

Mỗi lần bot cần số điện thoại, gọi API SMS mất **2–5 giây**. Nếu tải sẵn vào kho, bot lấy số tức thì — tăng tốc độ đăng ký đáng kể.

### Cách dùng

1. Bấm **`[⬇️ Tải trước số]`**
2. Nhập số lượng cần tải (VD: `100`)
3. Bấm OK — bot bắt đầu gọi API tải số
4. Theo dõi log:
   ```
   Đang tải số thứ 1/100...
   ✅ Đã tải số: +81-90-XXXX-XXXX (Tổng kho: 1)
   ```
5. Sau khi tải xong, tích **`☑ Dùng số lấy trước`** trước khi bấm Bắt đầu

Dừng tải giữa chừng: Bấm **`[🛑 Dừng tải số]`**.

### Xử lý lỗi khi tải số

| Thông báo | Nguyên nhân | Xử lý |
|---|---|---|
| `Kho hết số, thử lại sau 15s` | API SMS tạm hết số | Chờ tự động |
| `Bị chặn IP (403), nghỉ 30s` | Gọi API quá nhanh | Chờ tự động |
| `Quá nhiều lỗi (30 lần). Dừng.` | API có vấn đề nghiêm trọng | Liên hệ nhà cung cấp SMS |

---

## 8. Xử lý lỗi thường gặp

---

### ❌ Lỗi Bước 1 — Vào trang chủ thất bại

```
Lỗi Bước 1 (Vào trang chủ): TimeoutError
```

**Nguyên nhân:** Proxy chết / trang web Namco Parks bị sập / mạng yếu

**Xử lý:**
1. Mở sheet `Proxies`, xóa các proxy `dead`, thêm proxy mới còn sống
2. Giảm số Worker xuống để giảm tải proxy
3. Chờ 10–30 phút rồi chạy lại nếu nghi trang web bị sập

---

### ❌ Lỗi Bước 3 — Không nhận được OTP Email

```
Lỗi Bước 3 (OTP Email): Không nhận được OTP sau 120s
```

**Nguyên nhân:** Mật khẩu email sai / email bị khóa / OTP vào Spam / Bandai delay

**Xử lý:**
1. Kiểm tra lại mật khẩu ở cột `email_password`
2. Thử đăng nhập email bằng tay xem còn hoạt động không
3. Đăng nhập email thật → Vào Spam → Đánh dấu "Not spam"
4. Tăng timeout trong `config.json`: `"email_otp_timeout": 300`

---

### ❌ Lỗi Bước 3 — Email đã được sử dụng

```
Lỗi Bước 3: Email đã được sử dụng — FAIL_NO_RETRY
```

**Nguyên nhân:** Email này đã đăng ký Bandai Namco ID trước đó.

**Xử lý:** Email bị đánh `FAIL_NO_RETRY` — bot không chạy lại. Phải dùng email khác.

---

### ❌ Lỗi Bước 4 — API SMS hết số hoặc hết tiền

```
Lỗi Bước 4 (Thuê số SMS): API hết số hoặc bị lỗi
```

**Xử lý:**
1. Đăng nhập tài khoản SMS API → nạp thêm tiền
2. Kiểm tra `sms_api_key_expires` trong `config.json` xem key còn hạn không
3. Dùng tính năng Tải trước số để tích kho

---

### ❌ Lỗi Bước 5 — Xác thực SMS thất bại

```
Lỗi Bước 5 (Xác thực SMS): Không nhận được SMS OTP
```

**Nguyên nhân:** Số điện thoại ảo không nhận được SMS từ Bandai — lỗi bình thường, tỷ lệ ~5–10%.

**Xử lý:** Khi chạy lại, bot tự thuê số điện thoại **khác** và thử lại.

---

### ❌ Bot không start — "Chưa chọn file dữ liệu"

**Xử lý:** Bấm `[Chọn file]` và trỏ đến file XLSX.

---

### ❌ File XLSX lỗi "Permission denied"

**Nguyên nhân:** File đang được mở bởi Excel hoặc phần mềm khác.

**Xử lý:** Đóng file Excel → Khởi động lại bot.

---

## 9. Kế hoạch chạy batch lớn

### Kế hoạch chạy 1000 tài khoản / 3 ngày

#### Ngày 1 — Chuẩn bị

- [ ] Chuẩn bị file XLSX với 1000 email Outlook
- [ ] Chuẩn bị ít nhất 200 proxy Nhật còn hoạt động
- [ ] Nạp tiền SMS API đủ cho ~1100 số (dự phòng 10% lỗi)
- [ ] Tải trước 200 số điện thoại vào kho (Prefetch)
- [ ] Test thử 10 email đầu tiên (`Số lượng chạy = 10`)

#### Ngày 2 — Chạy batch đầu (500 tài khoản)

| Thời gian | Việc làm |
|---|---|
| 08:00 | Tải trước thêm 200 số điện thoại |
| 09:00 | Chạy 500 email đầu — Worker: 10, bật Headless |
| 09:00–12:00 | Theo dõi log mỗi 30 phút |
| 12:00 | Nghỉ trưa — bot tiếp tục chạy nền |
| 15:00 | Kiểm tra tiến độ, thêm proxy nếu cần |
| 18:00 | Dừng, kiểm tra kết quả sheet Accounts |
| 18:30 | Export danh sách SUCCESS ra file riêng |

#### Ngày 3 — Chạy batch 2 (500 tài khoản còn lại)

| Thời gian | Việc làm |
|---|---|
| 08:00 | Tải trước thêm 200 số điện thoại |
| 09:00 | Chạy 500 email tiếp (bot tự bỏ qua email đã SUCCESS) |
| 10:00–16:00 | Theo dõi, thêm proxy nếu cần |
| 17:00 | Dừng, kiểm tra kết quả |
| 17:30 | Chạy lại các email FAILED còn sót lại |

#### Ngày 4 — Hoàn thiện

- [ ] Chạy lại các email `FAILED` lần cuối (đổi proxy trước)
- [ ] Export file kết quả sạch (chỉ giữ SUCCESS)
- [ ] Backup file XLSX

---

### Công thức ước tính thời gian

```
Thời gian (giờ) = Tổng email ÷ (Workers × 60 ÷ phút_mỗi_tài_khoản)
```

*`phút_mỗi_tài_khoản` ≈ 3–5 phút (bao gồm chờ OTP và SMS)*

| Số email | Workers | Thời gian ước tính |
|:---:|:---:|:---:|
| 100 | 5 | ~1–1.5 giờ |
| 500 | 10 | ~2.5–4 giờ |
| 1,000 | 10 | ~5–8 giờ |
| 1,000 | 15 | ~3.5–5 giờ |

---

### Checklist trước mỗi phiên chạy

```
□ File XLSX đã đóng (không mở trong Excel)
□ Đủ proxy còn hoạt động trong sheet Proxies
□ SMS API còn số dư
□ Đã tải trước số điện thoại (nếu bật chế độ này)
□ Ngày sinh mặc định điền đúng format YYYY-MM-DD
□ Chọn đúng sheet Outlooks / Gmails / Iclouds
□ Số Worker phù hợp với máy tính
□ Bật Headless khi chạy thật
□ Kết nối mạng ổn định
```

---

## 10. Cấu hình nâng cao (config.json)

File `config.json` nằm cùng thư mục với phần mềm. Mở bằng Notepad hoặc VSCode để chỉnh thêm.

> ⚠️ **Cảnh báo:** Chỉ chỉnh khi hiểu rõ từng tham số. Sai cú pháp JSON sẽ khiến bot không khởi động được.

### Danh sách tham số

| Key | Kiểu | Mặc định | Mô tả |
|---|:---:|---|---|
| `headless` | bool | `true` | Bật/tắt chế độ ẩn trình duyệt |
| `use_proxy` | bool | `true` | Bật/tắt dùng proxy |
| `worker_count` | int | `3` | Số worker chạy song song |
| `default_dob` | string | `"1990-11-12"` | Ngày sinh mặc định (YYYY-MM-DD) |
| `default_prefecture` | string | `"愛知県"` | Tỉnh mặc định |
| `default_nickname` | string | `"..."` | Biệt danh mặc định |
| `default_password` | string | `"Namco2025!"` | Mật khẩu Namco mặc định |
| `email_otp_timeout` | int | `200` | Thời gian chờ OTP email (giây) |
| `sms_otp_timeout` | int | `300` | Thời gian chờ OTP SMS (giây) |
| `max_accounts_per_proxy` | int | `2` | Số tài khoản tối đa mỗi proxy |
| `use_pre_fetched_numbers` | bool | `false` | Dùng số đã tải sẵn |
| `xlsx_path` | string | `""` | Đường dẫn file XLSX |
| `active_sheet` | string | `"Outlooks"` | Sheet đang chạy |
| `browser_path` | string | `""` | Đường dẫn trình duyệt |
| `sms_api_key` | string | `""` | API key dịch vụ SMS |
| `sms_country` | string | `"jpn"` | Mã quốc gia cho số điện thoại |
| `keep_browser_open` | bool | `false` | Giữ trình duyệt mở sau khi xong |

### Ví dụ config tối ưu cho batch lớn

```json
{
  "headless": true,
  "use_proxy": true,
  "worker_count": 10,
  "email_otp_timeout": 200,
  "sms_otp_timeout": 300,
  "max_accounts_per_proxy": 2,
  "use_pre_fetched_numbers": true,
  "default_dob": "1992-07-15",
  "default_prefecture": "愛知県",
  "keep_browser_open": false
}
```

---

## Phụ lục A — Danh sách tỉnh Nhật

| Tên tiếng Nhật | Vùng |
|:---:|---|
| `北海道` | Hokkaido |
| `青森県` | Tohoku |
| `岩手県` | Tohoku |
| `宮城県` | Tohoku |
| `秋田県` | Tohoku |
| `山形県` | Tohoku |
| `福島県` | Tohoku |
| `茨城県` | Kanto |
| `栃木県` | Kanto |
| `群馬県` | Kanto |
| `埼玉県` | Kanto |
| `千葉県` | Kanto |
| `東京都` | Kanto — Thủ đô |
| `神奈川県` | Kanto |
| `新潟県` | Chubu |
| `富山県` | Chubu |
| `石川県` | Chubu |
| `福井県` | Chubu |
| `山梨県` | Chubu |
| `長野県` | Chubu |
| `岐阜県` | Chubu |
| `静岡県` | Chubu |
| `愛知県` | Chubu — **Mặc định bot** |
| `三重県` | Kinki |
| `滋賀県` | Kinki |
| `京都府` | Kinki |
| `大阪府` | Kinki |
| `兵庫県` | Kinki |
| `奈良県` | Kinki |
| `和歌山県` | Kinki |
| `鳥取県` | Chugoku |
| `島根県` | Chugoku |
| `岡山県` | Chugoku |
| `広島県` | Chugoku |
| `山口県` | Chugoku |
| `徳島県` | Shikoku |
| `香川県` | Shikoku |
| `愛媛県` | Shikoku |
| `高知県` | Shikoku |
| `福岡県` | Kyushu |
| `佐賀県` | Kyushu |
| `長崎県` | Kyushu |
| `熊本県` | Kyushu |
| `大分県` | Kyushu |
| `宮崎県` | Kyushu |
| `鹿児島県` | Kyushu |
| `沖縄県` | Okinawa |

---

## Phụ lục B — FAQ

**Q: Bot có thể chạy 24/7 không?**  
A: Được. Bật Headless → bot chạy nền liên tục. Tuy nhiên nên dừng 1–2 tiếng mỗi 8 tiếng để tránh proxy bị đốt.

**Q: Nếu máy tính tắt giữa chừng thì sao?**  
A: Không mất dữ liệu. Mọi email đang `PROCESSING` sẽ tự reset về `PENDING` khi khởi động lại bot.

**Q: Email đã SUCCESS có bị chạy lại không?**  
A: Không. Bot tự bỏ qua các email có status `SUCCESS` và `FAIL_NO_RETRY`.

**Q: Muốn thêm email mới trong khi bot đang chạy có được không?**  
A: Được. Thêm vào cuối sheet Outlooks (cột A và B), để trống cột status. Bot đọc thêm ở batch tiếp theo.

**Q: File XLSX lớn quá (>10MB) có bị chậm không?**  
A: Bot đọc từng batch 50 email một lần nên không ảnh hưởng nhiều. Nên chia file nếu có >5000 dòng.

**Q: Tỷ lệ thành công trung bình là bao nhiêu?**  
A: Thông thường 85–95% nếu proxy tốt và email còn hoạt động. Lỗi chủ yếu do proxy chết hoặc SMS không nhận được.

**Q: Có thể chạy nhiều phiên bot cùng lúc không?**  
A: Không nên. Chỉ chạy 1 phiên tại một thời điểm để tránh xung đột ghi file XLSX.

---

*Tài liệu này được tạo dựa trên phiên bản NamcoBot hiện tại. Nếu giao diện thay đổi, một số mô tả có thể khác đôi chút.*
