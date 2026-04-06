"""WebSocket consumer for real-time notifications."""
import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer that joins each authenticated user to their personal
    notification group (user_{user_id}).
    """

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        self.user_id = user.pk
        self.group_name = f"user_{self.user_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.debug("WebSocket connected: user=%d", self.user_id)

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.debug("WebSocket disconnected: code=%s", close_code)

    async def receive(self, text_data=None, bytes_data=None):
        # Client messages are not expected; ignore them
        pass

    async def notification_message(self, event):
        """Handle messages sent to the group via channel_layer.group_send."""
        await self.send(text_data=json.dumps({
            "event_type": event["event_type"],
            "payload": event["payload"],
        }))
