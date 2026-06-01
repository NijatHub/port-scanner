"""
Async port-scanning engine.

Supports both sync and async progress callbacks so the caller can do
async work (DB writes, WebSocket pushes) inside the scan loop without
blocking the event loop.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Callable, Coroutine, Optional, Union

from django.conf import settings

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT: float = getattr(settings, "SCANNER_CONNECT_TIMEOUT", 0.5)
MAX_CONCURRENCY: int   = getattr(settings, "SCANNER_MAX_CONCURRENCY", 200)

_BANNER_PORTS: set[int] = {21, 22, 25, 80, 110, 143, 443, 3306, 5432, 6379, 8080}


@dataclass
class PortResult:
    ip: str
    port: int
    open: bool
    banner: str = ""


async def _probe_port(
    ip: str,
    port: int,
    semaphore: asyncio.Semaphore,
    timeout: float,
) -> PortResult:
    async with semaphore:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=timeout,
            )
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return PortResult(ip=ip, port=port, open=False)

        banner = ""
        if port in _BANNER_PORTS:
            try:
                data = await asyncio.wait_for(reader.read(256), timeout=0.3)
                banner = data.decode(errors="replace").strip()[:200]
            except Exception:
                pass

        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

        return PortResult(ip=ip, port=port, open=True, banner=banner)


async def scan_ports_async(
    ip: str,
    port_start: int,
    port_end: int,
    *,
    timeout: float = CONNECT_TIMEOUT,
    max_concurrency: int = MAX_CONCURRENCY,
    progress_callback: Optional[Callable] = None,
) -> list[PortResult]:
    """
    Scan ip for open TCP ports in [port_start, port_end].

    progress_callback can be either:
      - a plain  callable(scanned, total, result)         — called normally
      - an async callable(scanned, total, result)         — awaited properly

    Using an async callback is strongly preferred: it lets you do async DB
    writes and channel pushes without blocking the event loop.
    """
    ports     = list(range(port_start, port_end + 1))
    total     = len(ports)
    semaphore = asyncio.Semaphore(max_concurrency)
    tasks     = [_probe_port(ip, port, semaphore, timeout) for port in ports]
    results: list[PortResult] = []
    scanned = 0

    for coro in asyncio.as_completed(tasks):
        result = await coro
        results.append(result)
        scanned += 1

        if progress_callback is not None:
            try:
                ret = progress_callback(scanned, total, result)
                # If callback returned a coroutine, await it properly
                if inspect.isawaitable(ret):
                    await ret
            except Exception:
                logger.exception("progress_callback raised an exception")

    results.sort(key=lambda r: r.port)
    return results