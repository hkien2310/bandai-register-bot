import random
from playwright.async_api import Page
from src.utils.logger import get_logger

log = get_logger("step1_connect")


async def run_step1(page: Page) -> bool:
    """
    Step 1: Vào trang chủ Namco Parks + click đăng ký thành viên
    """
    log.info("1. Vào trang chủ Namco Parks để giả lập người dùng thật...")
    try:
        await page.goto(
            "https://parks2.bandainamco-am.co.jp/",
            wait_until="commit",
            timeout=60000,
        )
        # Delay dài hơn để giả lập người dùng đọc trang chủ
        wait_ms = random.randint(3000, 5000)
        log.info(f"   Đã vào trang chủ Namco Parks. Đợi {wait_ms}ms...")
        await page.wait_for_timeout(wait_ms)
    except Exception as e:
        log.warning(f"   Vào trang chủ gặp lỗi: {e}. Thử lại...")
        await page.goto("https://parks2.bandainamco-am.co.jp/", wait_until="commit", timeout=60000)

    log.info("2. Click link '新規会員登録' trên trang chủ...")
    connect_link = await page.wait_for_selector(
        "a:has-text('新規会員登録'), a[href*='bandainamco_id_connect.html']",
        timeout=20000,
    )
    # Delay nhỏ trước khi click như người dùng thật
    await page.wait_for_timeout(random.randint(800, 1500))
    await connect_link.click()
    await page.wait_for_load_state("domcontentloaded", timeout=20000)
    log.info(f"   URL hiện tại: {page.url}")
    return True
