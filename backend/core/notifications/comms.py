"""Internal communications service client.

Placeholder for sending messages to the organization's internal messaging
platform (e.g., Rocket.Chat, Slack, Teams, etc.).

To integrate:
    1. Set COMMS_WEBHOOK_URL in backend/.env
    2. Implement _post_message() with your platform's webhook/API format
    3. Optionally set COMMS_CHANNEL for the target channel/room
"""

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

WEBHOOK_URL = os.getenv("COMMS_WEBHOOK_URL")
CHANNEL = os.getenv("COMMS_CHANNEL", "#skynet-notifications")
ENABLED = bool(WEBHOOK_URL)


def send_message(text: str, channel: Optional[str] = None) -> bool:
    """Send a message to the internal communications service.

    Args:
        text: Message body (supports markdown).
        channel: Target channel/room. Defaults to COMMS_CHANNEL env var.

    Returns:
        bool: True if sent successfully, False otherwise.
    """
    if not ENABLED:
        logger.debug("Comms not configured (COMMS_WEBHOOK_URL not set), skipping: %s", text[:80])
        return False

    target = channel or CHANNEL

    try:
        # Adapt this payload to your messaging platform:
        #
        # Rocket.Chat:
        #   {"text": "...", "channel": "#room"}
        #
        # Slack:
        #   {"text": "...", "channel": "#room"}
        #
        # Teams:
        #   {"text": "..."}  (channel set in webhook URL)
        #
        payload = {
            "text": text,
            "channel": target,
        }

        resp = requests.post(
            WEBHOOK_URL,  # type: ignore[arg-type]
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Comms message sent to %s", target)
        return True

    except Exception as exc:
        logger.warning("Failed to send comms message: %s", exc)
        return False
