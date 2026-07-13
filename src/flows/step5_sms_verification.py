import re
import time
import asyncio
import src.config as config
import src.core.sms_service as sms_service
from playwright.async_api import Page
from src.utils.logger import get_logger


log = get_logger("step5_sms_verification")

async def run_step5(page: Page, phone: str, pkey: str) -> str:
    """
    Step 5: Xác thực SMS OTP (Poll mã, tự động điền, tạm dừng chờ kiểm tra).
    """
    log.info("1. Chờ trang nhập mã SMS OTP...")

    # Chờ ô nhập OTP SMS xuất hiện
    try:
        otp_input = await page.wait_for_selector(
            "input[name='verification_code'], input[name='sms_code'], "
            "input[name='otp'], input[name='code'], input[type='text']",
            timeout=60000,
        )
        log.info(f"   Tìm thấy ô nhập OTP SMS tại URL: {page.url}")
    except Exception:
        log.warning("   Không tìm thấy ô OTP theo selector chuẩn, thử input text đầu tiên...")
        inputs = await page.query_selector_all("input[type='text'], input[type='number']")
        if inputs:
            otp_input = inputs[0]
        else:
            sc_path = str(config.DATA_DIR / f"err_sms_input_{int(time.time())}.png")
            await page.screenshot(path=sc_path)
            log.error(f"❌ Không tìm thấy ô nhập OTP SMS! Screenshot: {sc_path}")
            raise RuntimeError("Không tìm thấy ô nhập OTP SMS!")

    # ─── Poll SMS OTP ───
    otp_code = None
    if config.SMS_ENABLED and pkey not in ("MANUAL", ""):
        log.info(f"2. Poll SMS OTP từ API cho số {phone} (pkey: {pkey[:12]}...)...")
        try:
            timeout = config.SMS_OTP_TIMEOUT
            poll_interval = 4
            deadline = time.time() + timeout
            resend_clicked = False
            apikey = sms_service._get_apikey()

            while time.time() < deadline:
                try:
                    def call_api():
                        import requests
                        resp = requests.get(
                            f"{sms_service._BASE}/api/ext/getSms",
                            params={"apikey": apikey, "pkey": pkey},
                            timeout=10,
                        )
                        return resp.json()
                    
                    data = await asyncio.get_running_loop().run_in_executor(None, call_api)
                    
                    if data.get("status") == "error":
                        msg = data.get("msg", "") or data.get("message", "")
                        is_key_error = any(x in msg.lower() for x in ["api key", "hết hạn", "hợp lệ", "invalid", "expire"])
                        if is_key_error:
                            sms_service.invalidate_apikey()
                            log.info("API Key hết hạn hoặc không hợp lệ khi poll OTP (Flow), đang lấy lại key mới...")
                            apikey = sms_service._get_apikey(force_refresh=True)
                            continue

                    otp = data.get("otp", "")
                    state = data.get("state", "")
                    log.debug(f"  getSms: state='{state}' otp='{otp}'")
                    
                    if otp and state == "Hoàn thành":
                        otp_code = otp
                        log.info(f"✅ Nhận được SMS OTP: {otp_code}")
                        break
                except Exception as api_err:
                    log.warning(f"  getSms API error: {api_err}")
                
                # Sau 60 giây, nếu chưa nhận được mã thì click gửi lại (retry otp on web)
                elapsed = timeout - int(deadline - time.time())
                if elapsed >= 60 and not resend_clicked:
                    log.info("⏳ Đã qua 60s chưa có OTP. Click '認証コードの再送信' (Gửi lại OTP trên web)...")
                    try:
                        resend_btn = await page.query_selector(
                            "button:has-text('認証コードの再送信'), button:has-text('再送信'), "
                            "input[value*='再送信'], a:has-text('再送信'), [class*='resend'], [id*='resend']"
                        )
                        if resend_btn:
                            await resend_btn.click()
                            log.info("✅ Đã click gửi lại mã OTP trên web thành công.")
                            resend_clicked = True
                            await page.wait_for_timeout(2000)
                        else:
                            log.warning("❌ Không tìm thấy nút gửi lại mã OTP (認証コードの再送信).")
                    except Exception as btn_err:
                        log.warning(f"Lỗi khi click gửi lại mã: {btn_err}")

                remaining = int(deadline - time.time())
                if remaining <= 0:
                    break
                await asyncio.sleep(poll_interval)

            if otp_code:
                log.info(f"   → SMS OTP nhận được: {otp_code}. Điền vào form...")
                await otp_input.fill(str(otp_code))
                # Tự động click 認証する để hoàn thành đăng ký
                log.info("   Tự động click '認証する'...")
                auth_btn = await page.wait_for_selector(
                    "button:has-text('認証する'), input[type='submit'][value*='認証']",
                    timeout=60000
                )
                await auth_btn.click()
                
                # Chờ trang web chuyển hướng sau khi submit OTP
                try:
                    await page.wait_for_url("**/top.html*", timeout=60000)
                    log.info(f"✅ Đã về đích an toàn tại trang: {page.url}")
                except Exception:
                    log.error(f"❌ Lỗi: Sau khi nhập OTP, không thấy về trang top.html! URL hiện tại: {page.url}")
                    sc_path = str(config.DATA_DIR / f"err_sms_otp_fail_{int(time.time())}.png")
                    await page.screenshot(path=sc_path)
                    raise RuntimeError("SMS OTP verification failed: Không về được trang top.html")
            else:
                log.warning(f"   Hết timeout ({config.SMS_OTP_TIMEOUT}s) chưa có SMS OTP.")
                # Hủy số ngay lập tức trên API để được refund tiền
                log.info(f"   Hủy số {phone} trên API do hết hạn/không có OTP...")
                sms_service.cancel(pkey)
                
                # Tìm và click link đổi số để quay lại trang điền form
                log.info("   Đang click '携帯電話番号の変更はこちら' để quay lại form và đổi số...")
                change_btn = await page.query_selector(
                    "a:has-text('携帯電話番号の変更はこちら'), p:has-text('携帯電話番号の変更はこちら'), span:has-text('携帯電話番号 of 変更はこちら')"
                )
                if change_btn:
                    await change_btn.click()
                else:
                    log.warning("   Không tìm thấy nút quay lại, dùng page.goto để quay lại form...")
                    await page.goto("https://parks2.bandainamco-am.co.jp/member_regist_new.html")
                await page.wait_for_load_state("domcontentloaded", timeout=60000)
                raise RuntimeError("SMS_OTP_TIMEOUT")
        except Exception as e:
            if "SMS_OTP_TIMEOUT" in str(e):
                raise e
            log.error(f"   Lỗi poll SMS OTP: {e}")
    else:
        log.info("   SMS_ENABLED=false hoặc pkey=MANUAL. Bỏ qua tự động lấy OTP SMS.")
        # Nếu chạy thủ công, vẫn cần dừng để người dùng thao tác
        print("\n" + "=" * 70)
        print("⏸️  DỪNG Ở BƯỚC XÁC THỰC SMS OTP (THỦ CÔNG)")
        print("=" * 70)
        print(f"  Số điện thoại : {phone}")
        print("  Hãy điền OTP thủ công trên trình duyệt và xác nhận.")
        print("  Sau khi hoàn tất, nhấn [ENTER] tại đây để tiếp tục.")
        print("=" * 70 + "\n")
        await asyncio.to_thread(input, "Nhấn phím [ENTER] sau khi đã xác thực xong...")

    # Chờ một lúc cho chắc chắn
    await page.wait_for_timeout(3000)
    return True
