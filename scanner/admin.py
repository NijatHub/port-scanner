"""Admin configuration for the scanner app."""
from django.contrib import admin
from scanner.models import ScanJob, ScanResult


class ScanResultInline(admin.TabularInline):
    model = ScanResult
    extra = 0
    readonly_fields = ("ip", "port", "status", "banner", "timestamp")
    can_delete = False
    max_num = 0
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ScanJob)
class ScanJobAdmin(admin.ModelAdmin):
    list_display = (
        "id", "target", "resolved_ip",
        "port_start", "port_end",
        "status", "open_ports", "scanned_ports", "total_ports",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("target", "resolved_ip")
    readonly_fields = (
        "id", "resolved_ip", "celery_task_id",
        "created_at", "started_at", "completed_at",
        "open_ports", "scanned_ports", "total_ports", "progress_pct",
    )
    inlines = [ScanResultInline]
    ordering = ("-created_at",)


@admin.register(ScanResult)
class ScanResultAdmin(admin.ModelAdmin):
    list_display = ("job", "ip", "port", "status", "banner", "timestamp")
    list_filter = ("status", "timestamp")
    search_fields = ("ip", "port", "banner")
    ordering = ("job", "port")
    readonly_fields = ("job", "ip", "port", "status", "banner", "timestamp")
