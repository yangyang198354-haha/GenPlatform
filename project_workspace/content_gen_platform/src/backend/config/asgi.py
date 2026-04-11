"""ASGI config — supports HTTP and WebSocket via Django Channels."""
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from apps.notifications.routing import websocket_urlpatterns
from apps.notifications.middleware import JwtAuthMiddlewareStack

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

django_asgi_app = get_asgi_application()

# WebSocket authentication notes:
#
# 1. AllowedHostsOriginValidator removed: nginx validates the Host header
#    and restricts access to known upstreams; adding a second check here
#    causes 403s when clients connect via IP or non-standard ports.
#
# 2. AuthMiddlewareStack (session-based) replaced with JwtAuthMiddlewareStack:
#    the frontend uses Bearer JWT tokens, not session cookies.  WebSocket
#    connections cannot include HTTP headers, so the token is passed as a
#    URL query param: ws://host/ws/notifications/?token=<access_token>
application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JwtAuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        ),
    }
)
