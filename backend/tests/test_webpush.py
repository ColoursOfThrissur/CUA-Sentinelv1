import os
import sys
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.webpush_engine import WebPushEngine


def test_webpush_vapid_keypair():
    """Verify WebPushEngine auto-generates and returns valid VAPID keys."""
    engine = WebPushEngine()
    pub = engine.get_public_key()
    assert isinstance(pub, str)
    assert len(pub) > 40


def test_webpush_subscription_lifecycle():
    """Verify saving, listing, and removing push subscriptions in SQLite."""
    engine = WebPushEngine()
    test_endpoint = "https://fcm.googleapis.com/fcm/send/test-sub-12345"
    test_p256dh = "BCY9B2v9..."
    test_auth = "auth_secret_key"

    # 1. Save subscription
    saved = engine.save_subscription(
        endpoint=test_endpoint,
        p256dh=test_p256dh,
        auth=test_auth,
        user_agent="Chrome/128 Test Agent",
    )
    assert saved is True

    # 2. List subscriptions
    subs = engine.list_subscriptions()
    assert any(s["endpoint"] == test_endpoint for s in subs)

    # 3. Clean up
    engine.remove_subscription(test_endpoint)
    subs_after = engine.list_subscriptions()
    assert not any(s["endpoint"] == test_endpoint for s in subs_after)


def test_webpush_dispatch_empty():
    """Dispatch with no subscriptions returns gracefully without error."""
    engine = WebPushEngine()
    # ensure dummy test endpoint cleaned up
    engine.remove_subscription("https://fcm.googleapis.com/fcm/send/nonexistent")
    res = engine.dispatch_push("Test Title", "Test Body")
    assert "dispatched" in res
