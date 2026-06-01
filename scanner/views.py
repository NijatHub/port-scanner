"""
Views for the port-scanner application.

index        — landing page with the scan form
start_scan   — POST endpoint: validates input, creates ScanJob, enqueues task
scan_detail  — live-progress page (WebSocket-driven)
scan_status  — JSON polling fallback for non-WS clients
scan_history — paginated list of past scan jobs
"""
from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_GET

from scanner.forms import ScanRequestForm
from scanner.models import ScanJob, ScanResult
from scanner.tasks import run_scan_task
from scanner.validators import resolve_target, validate_port_range

logger = logging.getLogger(__name__)


# ── Landing / form ────────────────────────────────────────────────────────────

def index(request: HttpRequest) -> HttpResponse:
    form = ScanRequestForm()
    recent_jobs = ScanJob.objects.all()[:5]
    return render(request, "scanner/index.html", {"form": form, "recent_jobs": recent_jobs})


# ── Start scan ────────────────────────────────────────────────────────────────

@require_POST
def start_scan(request: HttpRequest) -> HttpResponse:
    form = ScanRequestForm(request.POST)
    if not form.is_valid():
        return render(request, "scanner/index.html", {"form": form})

    target = form.cleaned_data["target"].strip()
    port_start = form.cleaned_data["port_start"]
    port_end = form.cleaned_data["port_end"]

    # ── Server-side SSRF validation (belt-and-suspenders over form clean) ─────
    try:
        validate_port_range(port_start, port_end)
        resolve_target(target)   # raises ValidationError if unsafe
    except ValidationError as exc:
        messages.error(request, str(exc.message))
        return render(request, "scanner/index.html", {"form": form})

    job = ScanJob.objects.create(
        target=target,
        port_start=port_start,
        port_end=port_end,
        status=ScanJob.Status.PENDING,
    )

    task = run_scan_task.delay(str(job.pk))
    job.celery_task_id = task.id
    job.save(update_fields=["celery_task_id"])

    logger.info("Enqueued scan job %s → Celery task %s", job.pk, task.id)
    return redirect("scan_detail", job_id=job.pk)


# ── Live scan detail page ─────────────────────────────────────────────────────

def scan_detail(request: HttpRequest, job_id: str) -> HttpResponse:
    job = get_object_or_404(ScanJob, pk=job_id)
    open_results = job.results.filter(status=ScanResult.PortStatus.OPEN).order_by("port")
    return render(
        request,
        "scanner/scan_detail.html",
        {"job": job, "open_results": open_results},
    )


# ── JSON status endpoint (HTMX / polling fallback) ───────────────────────────

@require_GET
def scan_status(request: HttpRequest, job_id: str) -> JsonResponse:
    job = get_object_or_404(ScanJob, pk=job_id)
    open_results = list(
        job.results.filter(status=ScanResult.PortStatus.OPEN)
        .order_by("port")
        .values("port", "status", "banner", "timestamp")
    )
    return JsonResponse(
        {
            "status": job.status,
            "progress_pct": job.progress_pct,
            "scanned_ports": job.scanned_ports,
            "total_ports": job.total_ports,
            "open_ports": job.open_ports,
            "resolved_ip": job.resolved_ip,
            "error_message": job.error_message,
            "duration": job.duration_seconds,
            "open_results": open_results,
        }
    )


# ── Scan history ──────────────────────────────────────────────────────────────

def scan_history(request: HttpRequest) -> HttpResponse:
    qs = ScanJob.objects.prefetch_related("results").all()
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "scanner/history.html", {"page_obj": page})
