"""Generic webhook notification utility.

Sends POST requests with {"text": "..."} payload.
Compatible with Pumble, Slack, Feishu, Discord webhooks, etc.
"""

import logging
import os
import requests
from typing import List, Optional

logger = logging.getLogger(__name__)
PROXY_ENV_VARS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")
DIRECT_RETRY_EXCEPTIONS = (
    requests.exceptions.ProxyError,
    requests.exceptions.ConnectionError,
    requests.exceptions.ConnectTimeout,
)

try:
    from src.utils.config import WEBHOOK_URL
except ImportError:
    WEBHOOK_URL = ""


def _has_proxy_env() -> bool:
    return any(os.environ.get(name) for name in PROXY_ENV_VARS)


def _post_notification(url: str, message: str, *, trust_env: bool) -> None:
    session = requests.Session()
    session.trust_env = trust_env
    try:
        resp = session.post(url, json={"text": message}, timeout=10)
        resp.raise_for_status()
    finally:
        session.close()


def send_notification(message: str, webhook_url: Optional[str] = None) -> bool:
    """Send a text notification via webhook."""
    url = webhook_url or WEBHOOK_URL
    if not url:
        return False

    try:
        _post_notification(url, message, trust_env=True)
        logger.info("Webhook notification sent successfully")
        return True
    except DIRECT_RETRY_EXCEPTIONS as exc:
        if _has_proxy_env():
            logger.warning("Webhook notification failed via proxy/env; retrying direct: %s", exc)
            try:
                _post_notification(url, message, trust_env=False)
                logger.info("Webhook notification sent successfully without proxy/env")
                return True
            except Exception as direct_exc:
                logger.warning("Failed to send webhook notification without proxy/env: %s", direct_exc)
                return False
        logger.warning("Failed to send webhook notification: %s", exc)
        return False
    except Exception as exc:
        logger.warning("Failed to send webhook notification: %s", exc)
        return False


def notify_failures(stage: str, failures: List[str], webhook_url: Optional[str] = None) -> bool:
    """Send a batched failure notification for a pipeline stage."""
    if not failures:
        return False

    header = f"⚠️ PaperTools [{stage}] — {len(failures)} failures"
    details = "\n".join(f"  • {f}" for f in failures[:10])
    if len(failures) > 10:
        details += f"\n  ... and {len(failures) - 10} more"

    message = f"{header}\n{details}"
    return send_notification(message, webhook_url)


def notify_pipeline_complete(stats: dict, webhook_url: Optional[str] = None) -> bool:
    """Send a pipeline completion summary."""
    lines = ["✅ PaperTools pipeline complete"]
    for key, value in stats.items():
        lines.append(f"  • {key}: {value}")
    return send_notification("\n".join(lines), webhook_url)
