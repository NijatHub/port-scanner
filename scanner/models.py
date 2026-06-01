"""
Database models for the port-scanner application.

ScanJob  — one scan request (target + port range)
ScanResult — individual port probe outcome attached to a ScanJob
"""
import uuid
from django.db import models
from django.utils import timezone


class ScanJob(models.Model):
    """Represents a single user-initiated scan request."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    target = models.CharField(
        max_length=253,
        help_text="Resolved hostname or IPv4/IPv6 address",
    )
    resolved_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address the target resolved to at scan time",
    )
    port_start = models.PositiveIntegerField()
    port_end = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    celery_task_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Scan Job"
        verbose_name_plural = "Scan Jobs"

    def __str__(self) -> str:
        return f"ScanJob({self.target} {self.port_start}-{self.port_end}) [{self.status}]"

    @property
    def total_ports(self) -> int:
        return self.port_end - self.port_start + 1

    @property
    def scanned_ports(self) -> int:
        return self.results.count()

    @property
    def open_ports(self) -> int:
        return self.results.filter(status=ScanResult.PortStatus.OPEN).count()

    @property
    def progress_pct(self) -> int:
        if self.total_ports == 0:
            return 0
        return min(100, int(self.scanned_ports / self.total_ports * 100))

    @property
    def duration_seconds(self):
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class ScanResult(models.Model):
    """Stores the result of probing a single port within a ScanJob."""

    class PortStatus(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"
        FILTERED = "FILTERED", "Filtered"

    job = models.ForeignKey(ScanJob, on_delete=models.CASCADE, related_name="results")
    ip = models.GenericIPAddressField(help_text="Target IP at time of scan")
    port = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=PortStatus.choices, db_index=True)
    banner = models.CharField(
        max_length=256,
        blank=True,
        help_text="Optional service banner grabbed during connection",
    )
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        unique_together = [("job", "port")]
        ordering = ["port"]
        verbose_name = "Scan Result"
        verbose_name_plural = "Scan Results"
        indexes = [
            models.Index(fields=["job", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.ip}:{self.port} → {self.status}"
