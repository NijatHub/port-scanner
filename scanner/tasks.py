"""
Celery tasks for the port-scanner app.

Everything that touches the DB or WebSocket runs inside a single
asyncio.run() call, using:
  - sync_to_async()  for Django ORM calls  (no blocking the event loop)
  - channel_layer.group_send() awaited directly  (no async_to_sync)

This avoids the sync-inside-async deadlock that caused open ports to go
undetected in earlier versions.
"""
from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from celery import shared_task, Task
from channels.layers import get_channel_layer
from django.utils import timezone

from scanner.engine import PortResult, scan_ports_async
from scanner.models import ScanJob, ScanResult
from scanner.validators import resolve_target

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _group_name(job_id: str) -> str:
    return f"scan_{job_id}"


# DB helpers wrapped for async use
_get_job        = sync_to_async(ScanJob.objects.get, thread_sensitive=True)
_save_job       = sync_to_async(lambda job, fields: job.save(update_fields=fields), thread_sensitive=True)
_get_or_create  = sync_to_async(ScanResult.objects.get_or_create, thread_sensitive=True)
_bulk_create    = sync_to_async(
    lambda batch: ScanResult.objects.bulk_create(batch, ignore_conflicts=True),
    thread_sensitive=True,
)


async def _push(channel_layer, job_id: str, payload: dict[str, Any]) -> None:
    """Push an event to the job's WebSocket channel group."""
    if channel_layer is None:
        return
    try:
        await channel_layer.group_send(
            _group_name(job_id),
            {"type": "scan.event", "data": payload},
        )
    except Exception:
        logger.exception("WebSocket push failed for job %s", job_id)


# ── Main async scan logic ─────────────────────────────────────────────────────

async def _run_scan(job_id: str, celery_task_id: str) -> dict[str, Any]:
    """
    Full scan pipeline — runs inside a single asyncio.run() call so every
    await is clean and no sync code blocks the event loop.
    """
    channel_layer = get_channel_layer()

    # ── Load job ──────────────────────────────────────────────────────────────
    try:
        job = await _get_job(pk=job_id)
    except ScanJob.DoesNotExist:
        logger.error("ScanJob %s not found", job_id)
        return {"error": "job not found"}

    job.status         = ScanJob.Status.RUNNING
    job.started_at     = timezone.now()
    job.celery_task_id = celery_task_id
    await _save_job(job, ["status", "started_at", "celery_task_id"])
    await _push(channel_layer, job_id, {"type": "status", "status": "RUNNING"})

    # ── Resolve target ────────────────────────────────────────────────────────
    try:
        resolved_ip = await sync_to_async(resolve_target, thread_sensitive=True)(job.target)
        job.resolved_ip = resolved_ip
        await _save_job(job, ["resolved_ip"])
    except Exception as exc:
        await _fail_job(job, job_id, str(exc), channel_layer)
        return {"error": str(exc)}

    total_ports = job.total_ports
    await _push(channel_layer, job_id, {
        "type": "started",
        "resolved_ip": resolved_ip,
        "total_ports": total_ports,
    })

    # ── Progress callback (async — no sync/async mixing) ─────────────────────
    closed_batch: list[ScanResult] = []
    BATCH_SIZE = 50

    async def on_port(scanned: int, total: int, result: PortResult) -> None:
        nonlocal closed_batch
        pct = int(scanned / total * 100)

        if result.open:
            # Write to DB immediately → polling picks it up within 2 s
            await _get_or_create(
                job=job,
                port=result.port,
                defaults={
                    "ip": resolved_ip,
                    "status": ScanResult.PortStatus.OPEN,
                    "banner": result.banner,
                },
            )
            await _push(channel_layer, job_id, {
                "type": "port_result",
                "port": result.port,
                "status": ScanResult.PortStatus.OPEN,
                "banner": result.banner,
                "scanned": scanned,
                "total": total,
                "pct": pct,
            })

        else:
            closed_batch.append(ScanResult(
                job=job,
                ip=resolved_ip,
                port=result.port,
                status=ScanResult.PortStatus.CLOSED,
                banner="",
            ))
            if len(closed_batch) >= BATCH_SIZE:
                await _bulk_create(closed_batch)
                closed_batch.clear()

            if scanned % 25 == 0 or scanned == total:
                await _push(channel_layer, job_id, {
                    "type": "progress",
                    "scanned": scanned,
                    "total": total,
                    "pct": pct,
                })

    # ── Run the scanner ───────────────────────────────────────────────────────
    try:
        await scan_ports_async(
            resolved_ip,
            job.port_start,
            job.port_end,
            progress_callback=on_port,   # async callback — awaited cleanly
        )
    except Exception as exc:
        logger.exception("Scan engine failed for job %s", job_id)
        await _fail_job(job, job_id, str(exc), channel_layer)
        return {"error": str(exc)}

    # Flush remaining closed-port batch
    if closed_batch:
        await _bulk_create(closed_batch)

    # ── Finalise ──────────────────────────────────────────────────────────────
    job.status       = ScanJob.Status.COMPLETED
    job.completed_at = timezone.now()
    await _save_job(job, ["status", "completed_at"])

    open_count = await sync_to_async(lambda: job.open_ports, thread_sensitive=True)()
    await _push(channel_layer, job_id, {
        "type": "completed",
        "open_ports": open_count,
        "duration": job.duration_seconds,
    })

    return {"job_id": job_id, "status": "COMPLETED", "open_ports": open_count}


async def _fail_job(job, job_id, error, channel_layer) -> None:
    job.status        = ScanJob.Status.FAILED
    job.error_message = error
    job.completed_at  = timezone.now()
    await _save_job(job, ["status", "error_message", "completed_at"])
    await _push(channel_layer, job_id, {"type": "failed", "error": error})


# ── Celery entry point ────────────────────────────────────────────────────────

@shared_task(bind=True, name="scanner.tasks.run_scan_task", max_retries=0)
def run_scan_task(self: Task, job_id: str) -> dict[str, Any]:
    """
    Celery task entry point.  Runs the entire scan pipeline inside a
    single asyncio.run() so every operation is properly async.
    """
    import asyncio
    return asyncio.run(_run_scan(job_id, self.request.id or ""))