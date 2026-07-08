from playwright.async_api import Page
import src.config as config
from src.utils.logger import get_logger

log = get_logger("step2_bnid_click")

async def run_step2(page: Page, has_bnid: bool = False) -> bool:
    """
    Step 2: Tại trang kết nối, bấm nút vàng (đăng ký BNID mới) hoặc nút cam (đăng nhập)
    """
    log.info("1. Kiểm tra trang connect...")
    if "bandainamco_id_connect.html" not in page.url:
        log.warning(f"   URL hiện tại không khớp: {page.url}. Di chuyển trực tiếp...")
        await page.goto(
            "https://parks2.bandainamco-am.co.jp/ext/bandainamco_id_connect.html",
            wait_until="commit",
            timeout=30000,
        )

    # Chấp nhận cookie banner nếu có
    try:
        btn = await page.wait_for_selector(
            "#onetrust-accept-btn-handler, button:has-text('同意')",
            timeout=4000,
        )
        if btn:
            await btn.click()
            log.info("   Đã chấp nhận cookie banner.")
            await page.wait_for_timeout(800)
    except Exception:
        pass

    # Xác định nút để click dựa trên has_bnid
    if has_bnid:

        log.info("2. Click nút cam 'バンダイナムコIDでログイン'...")
        btn_selector = "a.btn-bnam-login, a[href*='login.html'], a[href*='logIn.html']"
    else:
        log.info("2. Click nút vàng 'バンダイナムコIDを取得'...")
        btn_selector = "a.btn-bnam-new, a[href*='signup.html'], a[href*='signUp.html']"

    yellow_btn = await page.wait_for_selector(btn_selector, timeout=20000)
    
    # Đảm bảo mở trong tab hiện tại, không mở tab mới
    await page.evaluate(
        f"""
        const a = document.querySelector("{btn_selector}");
        if (a) a.setAttribute('target', '_self');
        """
    )
    
    await yellow_btn.click()
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass
    log.info(f"   → Trang đăng ký/đăng nhập BNID: {page.url}")
    return True
