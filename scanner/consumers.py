"""
WebSocket consumer for live scan progress.

The frontend connects to ws://…/ws/scan/<job_id>/
The Celery task pushes events into the channel group; this consumer
forwards them to the connected browser client.
"""
from __future__ import annotations

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class ScanConsumer(AsyncWebsocketConsumer):
    async def connect(self) -> None:
        self.job_id = self.scope["url_route"]["kwargs"]["job_id"]
        self.group_name = f"scan_{self.job_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.debug("WS connected for job %s", self.job_id)

    async def disconnect(self, code: int) -> None:
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.debug("WS disconnected for job %s (code=%s)", self.job_id, code)

    # ── Receive events pushed by the Celery task ──────────────────────────────

    async def scan_event(self, event: dict) -> None:
        """Forward a scan event to the WebSocket client."""
        await self.send(text_data=json.dumps(event["data"]))

    # ── (optional) Handle messages from the client ────────────────────────────

    async def receive(self, text_data: str = "", bytes_data: bytes = b"") -> None:
        # Currently the client only listens; no inbound commands needed.
        pass
