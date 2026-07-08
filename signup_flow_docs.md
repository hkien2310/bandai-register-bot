# Hướng Dẫn Chi Tiết Quy Trình Đăng Ký Tài Khoản Namco Parks

Tài liệu này ghi lại chi tiết luồng đăng ký (signup flow) của hệ thống **Namco Parks Online Store** dựa trên giao diện thực tế của trang web.

---

## 📌 Khái Quát Quy Trình (Flow)
Quy trình đăng ký tài khoản gồm 2 giai đoạn chính:
1. Đăng ký **Bandai Namco ID** (Hệ thống tài khoản chung của hãng).
2. Hoàn thiện thông tin thành viên **Namco Parks** và xác thực số điện thoại qua **SMS OTP**.

---

## 🚀 Giai Đoạn 1: Đăng Ký Bandai Namco ID (Bắt buộc)

1. **Truy cập trang liên kết:**
   * URL: `https://parks2.bandainamco-am.co.jp/ext/bandainamco_id_connect.html`
   * Nhấp chọn nút màu vàng **新規登録 (Đăng ký mới / Banadainamco IDを取得)** ở bên trái.
2. **Điền thông tin tài khoản:**
   * **Email:** Điền địa chỉ email (sử dụng từ danh sách).
   * **Password:** Đặt mật khẩu cho tài khoản.
3. **Xác thực Email (Email Verification):**
   * Hệ thống sẽ gửi một mã xác nhận gồm **6 chữ số** về email đã nhập.
   * Lấy mã này và nhập lại vào trang web để kích hoạt tài khoản.
4. **Điền thông tin cơ bản:**
   * Chọn **Quốc gia/Khu vực** (Country/Territory) và vùng (ví dụ: Japan/Nhật Bản).
   * Nhập **Ngày / Tháng / Năm sinh**.
   * Đồng ý với các điều khoản dịch vụ (Terms of Service).
   * Tích chọn có chấp nhận theo dõi dữ liệu (Data Tracking Consent) hay không.

---

## 🚀 Giai Đoạn 2: Đăng Ký Thành Viên Namco Parks (member_regist_new.html)

Sau khi hoàn tất Giai đoạn 1, hệ thống tự động chuyển hướng về trang hoàn thiện thông tin của Namco Parks. Mày cần điền các thông tin sau:

| Trường Thông Tin | Trạng Thái | Mô Tả & Lưu Ý |
| :--- | :--- | :--- |
| **Biệt danh (ニックネーム)** | Bắt buộc (`必須`) | Tên hiển thị (ví dụ: `kien`). |
| **Email/ID (メールアドレス/ID)** | Bắt buộc (`必須`) | Email đã đăng ký ở giai đoạn 1 (tự động làm ID đăng nhập). |
| **Mật khẩu (パスワード)** | Bắt buộc (`必須`) | Nhập mật khẩu (từ 8 đến 20 ký tự, kết hợp chữ và số). Nhập lại 2 lần để xác nhận. |
| **Giới tính (性別)** | Tự chọn | Lựa chọn: Nam (`男性`), Nữ (`女性`), Khác (`あてはまらない`), Không trả lời/Ẩn (`回答しない/非表示`). <br>⚠️ *Lưu ý: Không thể thay đổi sau khi đăng ký.* |
| **Ngày sinh (生年月日)** | Bắt buộc (`必須`) | Chọn đúng Ngày / Tháng / Năm sinh. <br>⚠️ *Lưu ý: Không thể thay đổi sau khi đăng ký.* |
| **Khu vực sinh sống (お住まいの地域)** | Bắt buộc (`必須`) | Chọn Tỉnh/Thành phố của Nhật Bản (`都道府県`). |
| **Số điện thoại (携帯電話番号)** | Bắt buộc (`必須`) | Nhập số điện thoại di động (không chứa dấu gạch ngang `-`). Sử dụng để nhận mã xác thực **SMS**. |

### ⚠️ Lưu ý đặc biệt ở Giai đoạn 2:
* **Quy định độ tuổi (Sinh nhật):**
  * **Dưới 18 tuổi:** Bắt buộc phải có sự đồng ý của người bảo hộ. Giới hạn số tiền chi tiêu mua sắm mini-game/gashapon tối đa **20,000 Yên/tháng (đã gồm thuế)**.
  * **Từ 18 tuổi trở lên:** Không giới hạn mức chi tiêu.
* **Xác thực số điện thoại qua SMS:**
  * Bắt buộc phải thực hiện xác thực để hoàn tất đăng ký.
  * Hệ thống áp dụng quy tắc **1 số điện thoại = 1 tài khoản**. Không thể sử dụng lại số điện thoại đã đăng ký cho tài khoản khác.

---

## 🚀 Giai Đoạn 3: Xác Thực SMS & Hoàn Tất

1. Nhấp chọn đồng ý với **Điều khoản thành viên Namco Parks** và **Điều khoản chương trình tích điểm**.
2. Bấm nút màu đỏ **入力内容を確認する (Xác nhận thông tin nhập)** để chuyển sang trang xác nhận.
3. Nhận tin nhắn chứa mã OTP gửi về số điện thoại đã đăng ký.
4. Nhập mã OTP vào trang web để hoàn tất quy trình đăng ký thành viên. Hệ thống gửi email thông báo đăng ký thành công.
