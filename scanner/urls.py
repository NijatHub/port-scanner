"""URL configuration for the scanner app."""
from django.urls import path
from scanner import views

urlpatterns = [
    path("", views.index, name="index"),
    path("scan/start/", views.start_scan, name="start_scan"),
    path("scan/<str:job_id>/", views.scan_detail, name="scan_detail"),
    path("scan/<str:job_id>/status/", views.scan_status, name="scan_status"),
    path("history/", views.scan_history, name="scan_history"),
]
