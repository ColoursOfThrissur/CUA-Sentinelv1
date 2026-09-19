import os
import json
import base64
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from pywebpush import webpush, WebPushException
from db.connections import get_operational_db

logger = logging.getLogger(__name__)


class WebPushEngine:
    """
    Browser Web Push Notification Engine (RFC 8291 / RFC 8292).
    Manages VAPID EC keypair, registers client push subscriptions,
    and dispatches push alerts to registered browser workers.
    """

    def __init__(self):
        self._ensure_table()
        self.vapid_public_key, self.vapid_private_key = self._get_or_create_vapid_keys()

    def _ensure_table(self) -> None:
        conn = get_operational_db()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    subscription_id TEXT PRIMARY KEY,
                    endpoint TEXT UNIQUE NOT NULL,
                    p256dh TEXT NOT NULL,
                    auth TEXT NOT NULL,
                    user_agent TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                    last_delivered_at TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _get_or_create_vapid_keys(self) -> tuple[str, str]:
        """
        Retrieves VAPID keys from environment or notification_settings;
        if missing, auto-generates a standard SECP256R1 keypair and persists it.
        """
        env_pub = os.getenv("SENTINEL_VAPID_PUBLIC")
        env_priv = os.getenv("SENTINEL_VAPID_PRIVATE")
        if env_pub and env_priv:
            return env_pub, env_priv

        conn = get_operational_db()
        try:
            cur = conn.execute("SELECT key, value FROM notification_settings WHERE key IN ('vapid_public_key', 'vapid_private_key')")
            rows = dict(cur.fetchall())
            if "vapid_public_key" in rows and "vapid_private_key" in rows:
                return rows["vapid_public_key"], rows["vapid_private_key"]

            # Generate new SECP256R1 keypair
            pk = ec.generate_private_key(ec.SECP256R1())
            raw_priv = pk.private_numbers().private_value.to_bytes(32, 'big')
            b64_priv = base64.urlsafe_b64encode(raw_priv).decode().rstrip('=')

            raw_pub = pk.public_key().public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint
            )
            b64_pub = base64.urlsafe_b64encode(raw_pub).decode().rstrip('=')

            now = datetime.now(timezone.utc).isoformat()
            conn.execute("INSERT OR REPLACE INTO notification_settings (key, value, updated_at) VALUES ('vapid_public_key', ?, ?)", (b64_pub, now))
            conn.execute("INSERT OR REPLACE INTO notification_settings (key, value, updated_at) VALUES ('vapid_private_key', ?, ?)", (b64_priv, now))
            conn.commit()
            logger.info("Generated and stored new SECP256R1 VAPID keypair for Web Push notifications")
            return b64_pub, b64_priv
        finally:
            conn.close()

    def get_public_key(self) -> str:
        return self.vapid_public_key

    def save_subscription(self, endpoint: str, p256dh: str, auth: str, user_agent: Optional[str] = None) -> bool:
        import uuid
        conn = get_operational_db()
        try:
            sub_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO push_subscriptions (subscription_id, endpoint, p256dh, auth, user_agent)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(endpoint) DO UPDATE SET
                    p256dh = excluded.p256dh,
                    auth = excluded.auth,
                    user_agent = excluded.user_agent
                """,
                (sub_id, endpoint, p256dh, auth, user_agent or "Browser"),
            )
            conn.commit()
            logger.info(f"Registered WebPush subscription endpoint: {endpoint[:45]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to register push subscription: {e}")
            return False
        finally:
            conn.close()

    def list_subscriptions(self) -> List[Dict[str, Any]]:
        conn = get_operational_db()
        try:
            rows = conn.execute("SELECT * FROM push_subscriptions").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def remove_subscription(self, endpoint: str) -> None:
        conn = get_operational_db()
        try:
            conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
            conn.commit()
        finally:
            conn.close()

    def dispatch_push(self, title: str, body: str, url: str = "/", tag: str = "sentinel-alert") -> Dict[str, Any]:
        """Dispatches push message to all active browser endpoints."""
        subscriptions = self.list_subscriptions()
        if not subscriptions:
            return {"dispatched": 0, "active_subscriptions": 0}

        payload = json.dumps({
            "title": title,
            "body": body,
            "url": url,
            "tag": tag,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        success_count = 0
        dead_endpoints = []

        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub["endpoint"],
                        "keys": {
                            "p256dh": sub["p256dh"],
                            "auth": sub["auth"],
                        },
                    },
                    data=payload,
                    vapid_private_key=self.vapid_private_key,
                    vapid_claims={"sub": "mailto:admin@sentinel.local"},
                    timeout=5,
                )
                success_count += 1
            except WebPushException as ex:
                logger.warning(f"WebPush failed for {sub['endpoint'][:30]}: {ex}")
                # 404 or 410 indicates expired/unsubscribed browser token
                if ex.response is not None and ex.response.status_code in (404, 410):
                    dead_endpoints.append(sub["endpoint"])
            except Exception as e:
                logger.debug(f"Webpush error: {e}")

        for dead in dead_endpoints:
            self.remove_subscription(dead)

        return {
            "dispatched": success_count,
            "active_subscriptions": len(subscriptions) - len(dead_endpoints),
        }


webpush_engine = WebPushEngine()
