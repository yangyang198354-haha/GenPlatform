"""
JWT authentication middleware for Django Channels WebSocket connections.

Problem:
    Django's built-in AuthMiddlewareStack only reads session cookies.
    The frontend uses JWT tokens (Bearer auth) which are not sent via cookies.
    WebSocket connections cannot include arbitrary headers (no Authorization
    header), so the JWT token must be passed as a URL query parameter:
        ws://host/ws/notifications/?token=<access_token>

Solution:
    JwtAuthMiddlewareStack reads the `token` query param, validates it using
    the same simplejwt library used by the REST API, and attaches the
    authenticated User to scope["user"].

Usage (asgi.py):
    from apps.notifications.middleware import JwtAuthMiddlewareStack
    application = ProtocolTypeRouter({
        "websocket": URLRouter(websocket_urlpatterns),  # wrapped below
    })
    # wrap via JwtAuthMiddlewareStack(URLRouter(...))
"""
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


@database_sync_to_async
def _get_user_from_token(token_str: str):
    """Validate JWT access token and return the User or AnonymousUser."""
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        from django.contrib.auth import get_user_model

        token = AccessToken(token_str)
        user_id = token.get("user_id")
        if not user_id:
            return AnonymousUser()

        User = get_user_model()
        return User.objects.get(pk=user_id)
    except Exception as exc:
        logger.debug("WebSocket JWT auth failed: %s", exc)
        return AnonymousUser()


class JwtAuthMiddleware:
    """
    ASGI middleware that authenticates WebSocket connections via JWT.

    Reads ?token=<access_token> from the WebSocket URL query string.
    Sets scope["user"] to the authenticated User (or AnonymousUser).
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            query_string = scope.get("query_string", b"").decode()
            params = parse_qs(query_string)
            token_list = params.get("token", [])
            token_str = token_list[0] if token_list else ""

            if token_str:
                scope["user"] = await _get_user_from_token(token_str)
            else:
                scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)


def JwtAuthMiddlewareStack(inner):
    """Convenience wrapper — mirrors channels.auth.AuthMiddlewareStack."""
    return JwtAuthMiddleware(inner)
