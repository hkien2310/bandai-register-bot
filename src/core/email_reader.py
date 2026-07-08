import asyncio
from typing import Optional
from playwright.async_api import BrowserContext

from src.core.email_reader_imap import get_bandai_namco_otp_imap
from src.core.email_reader_web import get_bandai_namco_otp_web
from src.utils.logger import get_logger
import src.config as config

log = get_logger("email_reader")

async def get_bandai_namco_otp(
    context: BrowserContext,
    since_ts: float | None = None,
    timeout: int = 120,
    poll_interval: int = 5,
    target_email: str = "",
    target_password: str = "",
    mail_page: Optional[object] = None,
) -> str | None:
    """
    Router for getting Bandai Namco OTP.
    If the email is an Outlook/Hotmail account and we have a password, 
    use the Web Flow (Playwright) to avoid IMAP blocks.
    Otherwise, fallback to the traditional IMAP approach.
    """
    
    if since_ts is None:
        import time
        since_ts = time.time()
        
    is_outlook = target_email.lower().endswith(("@hotmail.com", "@outlook.com", "@live.com"))
    has_password = bool(target_password)
    
    if is_outlook and has_password:
        log.info(f"📧 Detecting Outlook/Hotmail account '{target_email}'. Routing to Web Flow...")
        return await get_bandai_namco_otp_web(
            context=context,
            since_ts=since_ts,
            timeout=timeout,
            poll_interval=poll_interval,
            target_email=target_email,
            target_password=target_password,
            mail_page=mail_page
        )
    else:
        log.info(f"📧 Routing '{target_email}' to traditional IMAP Flow...")
        return await get_bandai_namco_otp_imap(
            since_ts=since_ts,
            timeout=timeout,
            poll_interval=poll_interval,
            target_email=target_email,
            target_password=target_password
        )

# Re-export generate_account_email
from src.core.email_reader_imap import generate_account_email
