import asyncio
import argparse
import sys
import time
from pathlib import Path

# Thêm root path vào PYTHONPATH để import đúng các module
sys.path.append(str(Path(__file__).parent))

import src.config as config
from src.utils.logger import get_logger
from src.utils.proxy_pool import ProxyPool
from src.connections.xlsx_connection import XlsxConnection
from src.core.email_reader import generate_account_email
from src.worker import RegistrationWorker

log = get_logger("main")

async def run_worker_async(worker_id, email_queue, proxy_pool, sheets_manager):
    """Bọc RegistrationWorker.run chạy không đồng bộ hoàn toàn để tránh nghẽn log."""
    worker = RegistrationWorker(
        worker_id=worker_id,
        email_queue=email_queue,
        proxy_pool=proxy_pool,
        sheets_manager=sheets_manager
    )
    # Chạy worker.run() trong thread pool của asyncio để tránh block vòng lặp sự kiện chính
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, worker.run)

async def main_async():
    parser = argparse.ArgumentParser(description="Namco Parks Auto Registration Bot")
    parser.add_argument("--workers", type=int, default=None, help="Số luồng chạy song song")
    parser.add_argument("--test", action="store_true", help="Chạy chế độ test: chỉ lấy 1 email và thoát")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng account tối đa sẽ chạy trong lần này")
    args = parser.parse_args()



    log.info("="*50)
    log.info("🔥 BẮT ĐẦU CHẠY BOT ĐĂNG KÝ NAMCO PARKS")
    log.info("="*50)

    # 1. Cấu hình số luồng
    worker_count = 1 if args.test else (args.workers if args.workers is not None else config.WORKER_COUNT)
    
    # Xác định batch_size
    if args.test:
        batch_size = 1
    elif args.limit:
        batch_size = args.limit
    else:
        batch_size = 50
        
    log.info(f"Số luồng (workers): {worker_count}")
    if args.test:
        log.info("🛠 CHẾ ĐỘ TEST KÍCH HOẠT: Chỉ bốc 1 email rồi dừng.")
    elif args.limit:
        log.info(f"🚧 CHẾ ĐỘ GIỚI HẠN KÍCH HOẠT: Chỉ chạy {args.limit} email.")

    # 2. Khởi tạo XlsxConnection
    if not config.XLSX_PATH:
        log.error("❌ Chưa cấu hình đường dẫn file XLSX. Vui lòng mở GUI và chọn file XLSX trước.")
        return
    sheets_manager = XlsxConnection(config.XLSX_PATH)
    if not sheets_manager.is_connected():
        log.error("Không thể kết nối file XLSX. Kiểm tra lại đường dẫn. Dừng chương trình.")
        return

    # Auto-recover: reset PROCESSING → PENDING (các account bị dừng giữa chừng lần trước)
    sheets_manager.reset_processing_to_pending()

    # 3. Load proxies từ file XLSX
    if config.USE_PROXY:
        active_proxies = sheets_manager.get_active_proxies()
        proxy_pool = ProxyPool(active_proxies)
        # Khôi phục số lần sử dụng vĩnh viễn từ XLSX (account SUCCESS)
        sheets_manager.load_permanent_counts(proxy_pool)
    else:
        proxy_pool = ProxyPool([])

    from queue import Queue

    # 4. Kiểm tra số dư SMS trước khi chạy mass
    if config.SMS_ENABLED:
        from src.core.sms_service import check_balance
        balance = check_balance()
        if balance < 0:
            log.error("❌ Không lấy được số dư SMS (lấy API Key thất bại hoặc lỗi kết nối). Bot dừng để tránh lỗi đăng ký dở dang!")
            sys.exit(1)
        elif balance < 25:
            log.error(f"❌ Tài khoản SMS chỉ còn {balance} điểm/yên, không đủ để thuê số (giá ~25/số). Vui lòng nạp thêm tiền!")
            sys.exit(1)

    # 5. Vòng lặp chính: Đọc email PENDING từ Sheets và chạy
    while True:
        if config.STOP_FLAG:
            log.warning("🛑 Người dùng đã bấm Stop, dừng vòng lặp chính.")
            break

        # Lấy từng mẻ email để chạy
        emails_to_process = sheets_manager.get_pending_emails(batch_size=batch_size)
        
        if not emails_to_process:
            log.info("✅ Không còn tài khoản nào có trạng thái PENDING/Trống trên Sheets. Hoàn tất!")
            break

        email_queue = Queue()
        for email_data in emails_to_process:
            email_queue.put(email_data)

        log.info(f"Đang xử lý mẻ {len(emails_to_process)} email...")

        # Khởi chạy các worker không đồng bộ song song
        tasks = []
        for i in range(1, worker_count + 1):
            if config.STOP_FLAG:
                break
            tasks.append(run_worker_async(i, email_queue, proxy_pool, sheets_manager))
            
            # Chờ 2s nhưng check STOP_FLAG
            for _ in range(4):
                if config.STOP_FLAG: break
                await asyncio.sleep(0.5)

        # Luôn chờ các tiến trình con hoàn tất dù có lỗi hay người dùng STOP
        if tasks:
            try:
                await asyncio.gather(*tasks)
            except KeyboardInterrupt:
                log.warning("Nhận lệnh ngắt bàn phím (Ctrl+C). Đang dừng chương trình...")
                break
            
        if args.test or args.limit or config.STOP_FLAG:
            log.info("🛠 Đã hoàn thành mẻ giới hạn hoặc nhận lệnh STOP. Dừng chương trình.")
            break
            
        log.info("🔄 Hoàn thành mẻ hiện tại. Kiểm tra mẻ tiếp theo...")
        
        # Chờ 2s nhưng check STOP_FLAG
        for _ in range(4):
            if config.STOP_FLAG: break
            await asyncio.sleep(0.5)

    log.info("="*50)
    log.info("🎉 BOT ĐÃ HOÀN TẤT CHƯƠNG TRÌNH")
    log.info("="*50)

def main():
    # Buộc stdout flush liên tục
    import os
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
