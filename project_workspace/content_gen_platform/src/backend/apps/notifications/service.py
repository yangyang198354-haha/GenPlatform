"""WebSocket notification service using Django Channels."""
import json
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


async def push_notification(user_id: int, event_type: str, payload: dict) -> None:
    """Push a notification to a specific user's WebSocket channel."""
    channel_layer = get_channel_layer()
    group_name = f"user_{user_id}"
    try:
        await channel_layer.group_send(
            group_name,
            {
                "type": "notification.message",
                "event_type": event_type,
                "payload": payload,
            },
        )
    except Exception as e:
        logger.warning("Failed to push notification to user %d: %s", user_id, e)


def push_notification_sync(user_id: int, event_type: str, payload: dict) -> None:
    """Synchronous wrapper for push_notification (for use in sync contexts)."""
    async_to_sync(push_notification)(user_id, event_type, payload)
