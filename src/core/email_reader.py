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
    refresh_token: str = "",
    client_id: str = "",
    otp_email: str = "",
    otp_pass: str = "",
    provider: str = ""
) -> str | None:
    """
    Router for getting Bandai Namco OTP.
    If provider == 'outlooks', use DongVanFB API (if refresh_token exists) or Web Flow.
    If provider == 'gmails' or 'iclouds', use IMAP with App Password.
    """
    
    if since_ts is None:
        import time
        since_ts = time.time()
        
    if provider == "outlooks":
        if refresh_token and client_id:
            from src.core.email_reader_dongvanfb import get_bandai_namco_otp_dongvanfb
            log.info(f"📧 Detecting DongVanFB tokens for '{target_email}'. Routing to DongVanFB API Flow...")
            return await get_bandai_namco_otp_dongvanfb(
                email=target_email,
                refresh_token=refresh_token,
                client_id=client_id,
                timeout=timeout,
                poll_interval=poll_interval,
                since_ts=since_ts
            )
            
        has_password = bool(target_password)
        if has_password:
            log.info(f"📧 Detecting Outlook/Hotmail account '{target_email}' with password. Routing to Web Flow...")
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
            log.error(f"📧 Cannot fetch OTP for '{target_email}': Missing refresh_token and password.")
            return ""
            
    elif provider in ["gmails", "iclouds"]:
        log.info(f"📧 Routing '{target_email}' to traditional IMAP Flow ({provider})...")
        return await asyncio.to_thread(
            get_bandai_namco_otp_imap,
            target_email=target_email,
            otp_email=otp_email,
            otp_pass=otp_pass,
            timeout=timeout,
            since_ts=since_ts
        )
    else:
        # Fallback for old/unspecified provider
        log.warning(f"📧 Unknown provider '{provider}' for '{target_email}'. Trying IMAP fallback...")
        return await asyncio.to_thread(
            get_bandai_namco_otp_imap,
            target_email=target_email,
            otp_email=otp_email or target_email,
            otp_pass=otp_pass or target_password,
            timeout=timeout,
            since_ts=since_ts
        )

# Re-export generate_account_email
from src.core.email_reader_imap import generate_account_email
