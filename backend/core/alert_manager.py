import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import httpx

from db.connections import get_audit_db, get_operational_db

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Central Multi-Channel Notification Engine.
    Dispatches alerts to Discord Webhooks, Telegram Bot API, and WebSockets.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.http_client = httpx.AsyncClient(timeout=10.0)

    def _get_setting(self, key: str, default: str = "") -> str:
        try:
            conn = get_operational_db()
            cur = conn.execute("SELECT value FROM notification_settings WHERE key = ?", (key,))
            row = cur.fetchone()
            conn.close()
            if row:
                return row["value"]
        except Exception as e:
            logger.warning(f"Error fetching notification setting {key}: {e}")
        return default

    def set_setting(self, key: str, value: str) -> None:
        conn = get_operational_db()
        conn.execute(
            "INSERT OR REPLACE INTO notification_settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    async def dispatch_alert(
        self,
        title: str,
        message: str,
        severity: str = "INFO",
        category: str = "GENERAL",
        fields: Optional[Dict[str, str]] = None,
        link: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dispatches alert to Discord, Telegram, and logs to SQLite audit.
        severity: INFO (blue), WARNING (amber), CRITICAL (red), HITL (violet)
        """
        results = {"discord": False, "email": False, "audit_logged": False}

        # 1. Audit Logging
        try:
            conn = get_audit_db()
            conn.execute(
                """
                INSERT INTO system_events 
                (event_id, worker_id, boot_id, event_type, component, description, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt_{datetime.now(timezone.utc).timestamp()}",
                    self.config.get("system", {}).get("worker_id", "local_worker"),
                    "alert_mgr",
                    "SAFE_MODE_ENTERED" if severity == "CRITICAL" else "BOOT",
                    category,
                    f"[{severity}] {title}: {message}",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            conn.close()
            results["audit_logged"] = True
        except Exception as e:
            logger.warning(f"Failed to log alert to audit DB: {e}")

        # 2. Discord Webhook
        discord_url = self._get_setting("discord_webhook_url")
        if discord_url:
            results["discord"] = await self._send_discord(
                discord_url, title, message, severity, category, fields, link
            )

        # 3. SMTP Email Dispatch
        email_user = self._get_setting("smtp_user")
        app_password = self._get_setting("smtp_app_password")
        recipient_email = self._get_setting("recipient_email", email_user)

        if email_user and app_password and recipient_email:
            try:
                from core.email_engine import EmailEngine
                engine = EmailEngine()
                body_text = f"[{severity}] {title}\n\n{message}\n\nCategory: {category}\nTimestamp: {datetime.now(timezone.utc).isoformat()}"
                results["email"] = engine.send_email(
                    email_user=email_user,
                    app_password=app_password,
                    recipient_email=recipient_email,
                    subject=f"🛡️ Sentinel Alert: {title}",
                    body_text=body_text
                )
            except Exception as email_err:
                logger.warning(f"Failed sending alert email: {email_err}")

        return results

    async def _send_discord(
        self,
        webhook_url: str,
        title: str,
        message: str,
        severity: str,
        category: str,
        fields: Optional[Dict[str, str]],
        link: Optional[str],
    ) -> bool:
        color_map = {
            "INFO": 3447003,      # Blue
            "WARNING": 16753920,  # Amber
            "CRITICAL": 15158332, # Red
            "HITL": 10181046,     # Purple
        }

        embed_fields = []
        if fields:
            for k, v in fields.items():
                embed_fields.append({"name": k, "value": str(v), "inline": True})

        embed = {
            "title": f"🛡️ Sentinel Alert: {title}",
            "description": message,
            "color": color_map.get(severity.upper(), 3447003),
            "fields": embed_fields,
            "footer": {"text": f"CUA-Sentinel • Category: {category} • Severity: {severity}"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if link:
            embed["url"] = link

        payload = {"username": "CUA-Sentinel AI", "embeds": [embed]}

        try:
            res = await self.http_client.post(webhook_url, json=payload)
            if res.status_code in (200, 204):
                logger.info(f"Discord alert dispatched successfully: {title}")
                return True
            else:
                logger.error(f"Discord alert failed with status {res.status_code}: {res.text}")
        except Exception as e:
            logger.error(f"Error sending Discord webhook: {e}")
        return False

    async def _send_telegram(
        self,
        token: str,
        chat_id: str,
        title: str,
        message: str,
        severity: str,
        fields: Optional[Dict[str, str]],
    ) -> bool:
        icon = "🟢" if severity == "INFO" else "🟡" if severity == "WARNING" else "🔴"
        text = f"{icon} <b>CUA-Sentinel Alert</b>\n\n<b>{title}</b>\n{message}\n"
        if fields:
            text += "\n" + "\n".join([f"• <b>{k}:</b> {v}" for k, v in fields.items()])

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}

        try:
            res = await self.http_client.post(url, json=payload)
            if res.status_code == 200:
                logger.info(f"Telegram alert dispatched: {title}")
                return True
            else:
                logger.error(f"Telegram alert failed: {res.text}")
        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
        return False

    async def close(self):
        await self.http_client.aclose()
