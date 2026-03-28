"""Generic webhook notification utility.

Sends POST requests with {"text": "..."} payload.
Compatible with Pumble, Slack, Feishu, Discord webhooks, etc.
"""

import logging
import requests
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from src.utils.config import WEBHOOK_URL
except ImportError:
    WEBHOOK_URL = ""


def send_notification(message: str, webhook_url: Optional[str] = None) -> bool:
    """Send a text notification via webhook."""
    url = webhook_url or WEBHOOK_URL
    if not url:
        return False

    try:
        resp = requests.post(url, json={"text": message}, timeout=10)
        resp.raise_for_status()
        logger.info("Webhook notification sent successfully")
        return True
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
