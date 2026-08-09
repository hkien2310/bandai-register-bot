"""
Kịch bản kiểm tra xem hòm Gmail catch-all có nhận được mail gửi tới alias không.
Cú pháp: python3 tests/check_alias_mail.py <alias_email>
Ví dụ: python3 tests/check_alias_mail.py fine.affix-3n@icloud.com
"""
import sys
import imaplib
import email

OTP_EMAIL = "ank26511@gmail.com"
OTP_PASS = "hgcz vxyt byel zpxb"

def check_alias(target_alias: str):
    print(f"🔍 Đang kiểm tra hòm thư '{OTP_EMAIL}' cho alias '{target_alias}'...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=15)
        mail.login(OTP_EMAIL, OTP_PASS)
        mail.select("inbox")

        import time
        today_str = time.strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(FROM "noreply@id.banapassport.net" SINCE {today_str})')
        if status == "OK" and messages[0]:
            msg_nums = messages[0].split()[-20:]
            num_str = b",".join(msg_nums).decode()
            res, data = mail.fetch(num_str, "(BODY.PEEK[HEADER.FIELDS (TO DATE SUBJECT)])")
            
            found_count = 0
            if res == "OK" and data:
                for item in reversed(data):
                    if isinstance(item, tuple) and item[1]:
                        msg = email.message_from_bytes(item[1])
                        to_addr = str(msg.get("To", "")).lower()
                        if target_alias.lower() in to_addr:
                            found_count += 1
                            print(f"  ✅ [TÌM THẤY #{found_count}] Ngày: {msg.get('Date')} | To: {to_addr}")

            if found_count == 0:
                print(f"  ❌ KHÔNG TÌM THẤY email nào từ Bandai gửi đến '{target_alias}' trong 20 mail Bandai gần nhất!")
            else:
                print(f"  🎉 Tổng cộng tìm thấy {found_count} email cho alias này.")
        else:
            print("  ⚠️ Hòm thư rỗng hoặc không có mail từ Bandai.")

        mail.logout()
    except Exception as e:
        print(f"  ❌ Lỗi kết nối IMAP: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = "fine.affix-3n@icloud.com"
    check_alias(target)
