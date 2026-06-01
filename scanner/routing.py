"""WebSocket URL routing for the scanner app."""
from django.urls import re_path
from scanner.consumers import ScanConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/scan/(?P<job_id>[0-9a-f-]{36})/$",
        ScanConsumer.as_asgi(),
    ),
]
