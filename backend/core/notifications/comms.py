"""Internal communications service client.

Sends notifications to an operator-supplied webhook for the organization's
internal messaging platform.

To integrate:
    1. Set COMMS_WEBHOOK_URL in backend/.env
    2. Optionally set COMMS_CHANNEL for the target channel/room
    3. Adjust the JSON payload if your webhook format requires different keys
"""

import logging
import os

import requests  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

WEBHOOK_URL = os.getenv("COMMS_WEBHOOK_URL")
CHANNEL = os.getenv("COMMS_CHANNEL", "#skynet-notifications")
ENABLED = bool(WEBHOOK_URL)


def send_message(text: str, channel: str | None = None) -> bool:
    """Send a message to the internal comms webhook.

    Never raises: any transport/HTTP error is logged at WARNING and
    surfaced via the boolean return. When the webhook URL is not
    configured (``COMMS_WEBHOOK_URL`` unset) this is a no-op that
    returns ``False``.

    Args:
        text: Message body to deliver.
        channel: Optional override for the target channel; defaults to
            ``COMMS_CHANNEL`` (``#skynet-notifications``).

    Returns:
        ``True`` when the webhook accepted the payload, ``False`` when
        delivery was skipped or any error occurred.
    """
    if not ENABLED or not WEBHOOK_URL:
        logger.debug("Comms not configured (COMMS_WEBHOOK_URL not set), skipping: %s", text[:80])
        return False

    target = channel or CHANNEL
    try:
        payload = {
            "text": text,
            "channel": target,
        }

        resp = requests.post(
            WEBHOOK_URL,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Comms message sent to %s", target)
        return True

    except requests.RequestException as exc:
        logger.warning("Failed to send comms message: %s", exc)
        return False
