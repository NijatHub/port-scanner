# NetProbe — Async Django Port Scanner

A production-ready, security-hardened TCP port scanner built with Django,
Celery, Redis, Django Channels (WebSockets), and Python asyncio.

---

## Architecture

```
Browser ──── HTTP ────► Daphne (ASGI) ──► Django views
         │                   │
         └─── WebSocket ─────┘
                             │
                        Channel Layer (Redis)
                             │
                        Celery Worker ──► asyncio engine ──► TCP probes
                             │
                        SQLite / PostgreSQL
```

| Layer | Technology |
|-------|-----------|
| ASGI server | Daphne (HTTP + WebSocket) |
| Background tasks | Celery 5 + Redis broker |
| Real-time updates | Django Channels 4 (WebSocket) + polling fallback |
| Async I/O scanner | Python `asyncio.open_connection` with semaphore cap |
| SSRF protection | RFC-1918 / loopback / link-local block-list + DNS validation |
| Database | SQLite (dev) / PostgreSQL (prod) via `ScanJob` + `ScanResult` models |

---

## Features

- **Async TCP scanning** — scans up to 200 ports concurrently via `asyncio`
- **Real-time updates** — WebSocket stream with HTMX-style polling fallback
- **SSRF prevention** — 14 blocked network ranges including RFC-1918, loopback,
  link-local, multicast, documentation ranges
- **Rate limiting** — configurable max port range (default 1000) and concurrency cap
- **Banner grabbing** — opportunistic service banner retrieval on known ports
- **Service detection** — 50+ well-known port→service name mappings
- **Celery task hard-limits** — soft (270s) and hard (300s) time limits per scan task
- **Batch DB writes** — results bulk-created in groups of 50 for efficiency
- **Admin panel** — full `django.contrib.admin` integration

---

## Quick Start (Docker Compose)

```bash
git clone <repo>
cd portscanner

docker compose up --build
# Open http://localhost:8000
```

---

## Local Development

### Prerequisites

- Python 3.11+
- Redis (running locally on `localhost:6379`)

### Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Apply migrations
python manage.py migrate

# 4. Create a superuser (optional, for /admin)
python manage.py createsuperuser
```

### Run all services

You need **three terminal tabs**:

```bash
# Tab 1 — Redis (or use Docker)
redis-server

# Tab 2 — Django / Daphne
daphne -b 0.0.0.0 -p 8000 portscanner.asgi:application

# Tab 3 — Celery worker
celery -A portscanner worker -l info --concurrency=4
```

Then visit **http://localhost:8000**.

---

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | dev key | Django secret (change in prod!) |
| `DEBUG` | `True` | Django debug mode |
| `ALLOWED_HOSTS` | `localhost 127.0.0.1` | Space-separated allowed hosts |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `SCANNER_MAX_PORT_RANGE` | `1000` | Maximum ports per scan job |
| `SCANNER_CONNECT_TIMEOUT` | `0.5` | TCP connect timeout (seconds) |
| `SCANNER_MAX_CONCURRENCY` | `200` | Max simultaneous asyncio coroutines |

---

## Security Design

### SSRF Prevention

All targets are validated **twice**: once in the Django view (before job creation)
and once inside the Celery worker (before scanning begins).

Blocked ranges:

| Range | Reason |
|-------|--------|
| `127.0.0.0/8`, `::1` | Loopback |
| `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | RFC-1918 private |
| `169.254.0.0/16`, `fe80::/10` | Link-local / APIPA |
| `fc00::/7` | IPv6 unique local |
| `224.0.0.0/4`, `ff00::/8` | Multicast |
| `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` | Documentation |
| `100.64.0.0/10` | Shared address space (RFC 6598) |
| `0.0.0.0/8` | Unspecified |
| `240.0.0.0/4` | IANA reserved |

Hostnames are resolved with **dnspython** (bypassing the OS stub resolver),
and the resolved IP is checked against the block-list before scanning.

### Abuse Mitigation

- Hard cap on port range (default 1000, env-configurable)
- Celery task time limits (270s soft / 300s hard) prevent runaway scans
- Semaphore cap on asyncio concurrency

---

## Project Structure

```
portscanner/
├── manage.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
│
├── portscanner/            # Django project package
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py             # Daphne / Channels ASGI config
│   └── celery.py           # Celery app
│
├── scanner/                # Main Django app
│   ├── models.py           # ScanJob + ScanResult
│   ├── views.py            # index, start_scan, scan_detail, scan_status, scan_history
│   ├── forms.py            # ScanRequestForm with validation
│   ├── validators.py       # SSRF guards + port-range validation
│   ├── engine.py           # asyncio TCP scanner
│   ├── tasks.py            # Celery task (orchestrates scan + pushes WS events)
│   ├── consumers.py        # Django Channels WebSocket consumer
│   ├── routing.py          # WS URL routing
│   ├── admin.py
│   └── templatetags/
│       └── scanner_tags.py # well_known_service filter
│
└── templates/scanner/
    ├── base.html           # Terminal/cyberpunk design system
    ├── index.html          # Scan form + recent jobs
    ├── scan_detail.html    # Live progress (WS + polling fallback)
    └── history.html        # Paginated scan history
```

---

## Database Schema

```sql
-- ScanJob: one row per user-initiated scan
CREATE TABLE scanner_scanjob (
    id            UUID PRIMARY KEY,
    target        VARCHAR(253),      -- hostname or IP as entered
    resolved_ip   INET,              -- actual IP scanned
    port_start    INTEGER,
    port_end      INTEGER,
    status        VARCHAR(16),       -- PENDING|RUNNING|COMPLETED|FAILED
    celery_task_id VARCHAR(255),
    error_message TEXT,
    created_at    TIMESTAMPTZ,
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ
);

-- ScanResult: one row per (job, port) probe
CREATE TABLE scanner_scanresult (
    id        BIGSERIAL PRIMARY KEY,
    job_id    UUID REFERENCES scanner_scanjob(id) ON DELETE CASCADE,
    ip        INET,
    port      INTEGER,
    status    VARCHAR(10),           -- OPEN|CLOSED|FILTERED
    banner    VARCHAR(256),
    timestamp TIMESTAMPTZ
);
```

---

## Production Checklist

- [ ] Set `DEBUG=False` and `DJANGO_SECRET_KEY` to a strong random value
- [ ] Switch `DATABASES` to PostgreSQL
- [ ] Set `ALLOWED_HOSTS` to your real domain
- [ ] Add authentication (restrict who can launch scans)
- [ ] Add rate-limiting per user (e.g. `django-ratelimit`)
- [ ] Run Daphne behind nginx with TLS
- [ ] Use `CELERY_TASK_ALWAYS_EAGER=False` and monitor with Flower
- [ ] Audit logs for all scan requests
