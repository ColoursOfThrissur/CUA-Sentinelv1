import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from core.alert_manager import AlertManager
from core.email_engine import EmailEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notifications", tags=["notifications"])
alert_manager = AlertManager()
email_engine = EmailEngine()


class NotificationSettingPayload(BaseModel):
    discord_webhook_url: Optional[str] = None
    discord_bot_token: Optional[str] = None
    discord_allowed_user_id: Optional[str] = None
    discord_channel_id: Optional[str] = None
    smtp_user: Optional[str] = None
    smtp_app_password: Optional[str] = None
    recipient_email: Optional[str] = None


class TestAlertPayload(BaseModel):
    title: str = "Test Notification"
    message: str = "This is a test alert from CUA-Sentinel Multi-Channel Notification Engine."
    severity: str = "INFO"


@router.get("/settings")
def get_settings() -> Dict[str, str]:
    return {
        "discord_webhook_url": alert_manager._get_setting("discord_webhook_url"),
        "discord_bot_token": alert_manager._get_setting("discord_bot_token"),
        "discord_allowed_user_id": alert_manager._get_setting("discord_allowed_user_id"),
        "discord_channel_id": alert_manager._get_setting("discord_channel_id"),
        "smtp_user": alert_manager._get_setting("smtp_user"),
        "smtp_app_password": alert_manager._get_setting("smtp_app_password"),
        "recipient_email": alert_manager._get_setting("recipient_email"),
    }


@router.post("/settings")
def update_settings(payload: NotificationSettingPayload) -> Dict[str, str]:
    if payload.discord_webhook_url is not None:
        alert_manager.set_setting("discord_webhook_url", payload.discord_webhook_url)
    if payload.discord_bot_token is not None:
        alert_manager.set_setting("discord_bot_token", payload.discord_bot_token)
    if payload.discord_allowed_user_id is not None:
        alert_manager.set_setting("discord_allowed_user_id", payload.discord_allowed_user_id)
    if payload.discord_channel_id is not None:
        alert_manager.set_setting("discord_channel_id", payload.discord_channel_id)
    if payload.smtp_user is not None:
        alert_manager.set_setting("smtp_user", payload.smtp_user)
    if payload.smtp_app_password is not None:
        alert_manager.set_setting("smtp_app_password", payload.smtp_app_password)
    if payload.recipient_email is not None:
        alert_manager.set_setting("recipient_email", payload.recipient_email)
    return {"status": "SUCCESS"}


@router.post("/test")
async def send_test_alert(payload: TestAlertPayload) -> Dict[str, Any]:
    res = await alert_manager.dispatch_alert(
        title=payload.title,
        message=payload.message,
        severity=payload.severity,
        category="TEST",
        fields={"System": "CUA-Sentinel AI", "Triggered By": "User Settings Panel"},
    )
    return {"status": "DISPATCHED", "results": res}


@router.post("/test-discord-bot")
async def test_discord_bot() -> Dict[str, Any]:
    token = alert_manager._get_setting("discord_bot_token")
    if not token:
        raise HTTPException(status_code=400, detail="Discord Bot Token is empty. Please enter your Bot Token.")

    headers = {"Authorization": f"Bot {token.strip()}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.get("https://discord.com/api/v10/users/@me", headers=headers)
        if res.status_code == 200:
            bot_info = res.json()
            return {
                "status": "SUCCESS",
                "username": bot_info.get("username"),
                "bot_id": bot_info.get("id"),
                "message": f"Discord Bot Token Verified! Bot Name: {bot_info.get('username')}"
            }
        else:
            raise HTTPException(status_code=400, detail=f"Discord API returned status {res.status_code}. Please reset your Bot Token in Discord Developer Portal.")


@router.post("/test-gmail-sync")
def test_gmail_sync() -> Dict[str, Any]:
    email_user = alert_manager._get_setting("smtp_user")
    app_pass = alert_manager._get_setting("smtp_app_password")

    if not email_user or not app_pass:
        raise HTTPException(status_code=400, detail="Gmail username or App Password missing in settings.")

    try:
        messages = email_engine.fetch_recent_emails(email_user, app_pass, max_emails=3)
        return {
            "status": "SUCCESS",
            "message": f"Successfully connected to Gmail IMAP. Fetched {len(messages)} recent emails.",
            "emails": messages
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gmail IMAP connection failed: {str(e)}")


@router.post("/test-email")
def test_email_dispatch() -> Dict[str, Any]:
    email_user = alert_manager._get_setting("smtp_user")
    app_pass = alert_manager._get_setting("smtp_app_password")
    recipient = alert_manager._get_setting("recipient_email", email_user)

    if not email_user or not app_pass or not recipient:
        raise HTTPException(status_code=400, detail="Gmail credentials or recipient email missing.")

    try:
        sent = email_engine.send_email(
            email_user=email_user,
            app_password=app_pass,
            recipient_email=recipient,
            subject="🛡️ Sentinel Test Email",
            body_text="Hello! This is a test email notification from CUA-Sentinel AI."
        )
        return {"status": "SUCCESS", "sent": sent}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SMTP email dispatch failed: {str(e)}")
