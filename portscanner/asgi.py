"""
ASGI configuration — exposes the channel-aware application callable.
Handles both HTTP (Django) and WebSocket (Channels) traffic.
"""
import os
import django
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portscanner.settings")
django.setup()

from channels.auth import AuthMiddlewareStack          # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
import scanner.routing                                  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(scanner.routing.websocket_urlpatterns)
            )
        ),
    }
)
