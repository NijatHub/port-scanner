"""
Input validation helpers for the port scanner.

Goals
-----
1. Prevent SSRF — block RFC-1918 / link-local / loopback / special-use ranges.
2. Enforce port-range limits to prevent denial-of-service / abuse.
3. Resolve hostnames safely and return the canonical IPv4/v6 address.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Tuple

import dns.resolver
import dns.exception
from django.conf import settings
from django.core.exceptions import ValidationError


# ── Blocked network ranges (SSRF / abuse prevention) ─────────────────────────

_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    # Loopback
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    # Private / RFC-1918
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # Link-local (APIPA / IPv6 LL)
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
    # Unique local (IPv6)
    ipaddress.ip_network("fc00::/7"),
    # Multicast
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("ff00::/8"),
    # Documentation / test
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    # Shared address space (RFC 6598)
    ipaddress.ip_network("100.64.0.0/10"),
    # Unspecified / catch-all
    ipaddress.ip_network("0.0.0.0/8"),
    # IANA reserved
    ipaddress.ip_network("240.0.0.0/4"),
    # Localhost-alias IPv6
    ipaddress.ip_network("::ffff:127.0.0.0/104"),
]


def _is_blocked_ip(ip_str: str) -> bool:
    """Return True if *ip_str* falls inside any blocked network."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # can't parse → reject

    return any(addr in net for net in _BLOCKED_NETWORKS)


# ── Hostname / IP resolution ──────────────────────────────────────────────────

def resolve_target(raw_target: str) -> str:
    """
    Resolve *raw_target* (hostname or IP literal) to a safe IP string.

    Raises
    ------
    ValidationError
        • If the input is malformed / too long.
        • If resolution fails.
        • If the resolved IP is in a blocked range (SSRF guard).

    Returns
    -------
    str
        Canonical IP address string that is safe to scan.
    """
    target = raw_target.strip().lower()

    if not target:
        raise ValidationError("Target must not be empty.")

    if len(target) > 253:
        raise ValidationError("Target is too long (max 253 characters).")

    # ── Try to parse as a bare IP literal first ───────────────────────────────
    try:
        addr = ipaddress.ip_address(target)
        ip_str = str(addr)
        if _is_blocked_ip(ip_str):
            raise ValidationError(
                f"Target IP {ip_str!r} is in a restricted/private range and cannot be scanned."
            )
        return ip_str
    except ValueError:
        pass  # not a bare IP; treat as hostname

    # ── Hostname: validate characters before resolving ────────────────────────
    allowed_chars = set("abcdefghijklmnopqrstuvwxyz0123456789.-")
    if not all(c in allowed_chars for c in target):
        raise ValidationError(
            "Hostname contains invalid characters. "
            "Only letters, digits, hyphens, and dots are allowed."
        )

    # ── Resolve hostname → IP using dnspython (no OS resolver tricks) ─────────
    try:
        answers = dns.resolver.resolve(target, "A", lifetime=5)
        ip_str = str(answers[0])
    except dns.resolver.NXDOMAIN:
        raise ValidationError(f"Hostname {target!r} does not exist (NXDOMAIN).")
    except dns.resolver.NoAnswer:
        # Fallback: try AAAA
        try:
            answers = dns.resolver.resolve(target, "AAAA", lifetime=5)
            ip_str = str(answers[0])
        except Exception:
            raise ValidationError(f"No DNS records found for {target!r}.")
    except dns.exception.Timeout:
        raise ValidationError(f"DNS resolution timed out for {target!r}.")
    except Exception as exc:
        raise ValidationError(f"DNS resolution failed: {exc}")

    # ── SSRF check on the resolved address ────────────────────────────────────
    if _is_blocked_ip(ip_str):
        raise ValidationError(
            f"Hostname {target!r} resolves to a restricted IP ({ip_str}) "
            "and cannot be scanned."
        )

    return ip_str


# ── Port range validation ─────────────────────────────────────────────────────

MAX_PORT_RANGE: int = getattr(settings, "SCANNER_MAX_PORT_RANGE", 1000)


def validate_port_range(port_start: int, port_end: int) -> Tuple[int, int]:
    """
    Validate and return a normalised (port_start, port_end) tuple.

    Raises
    ------
    ValidationError
        On any constraint violation.
    """
    try:
        port_start = int(port_start)
        port_end = int(port_end)
    except (TypeError, ValueError):
        raise ValidationError("Port values must be integers.")

    if not (1 <= port_start <= 65535):
        raise ValidationError("Start port must be between 1 and 65535.")

    if not (1 <= port_end <= 65535):
        raise ValidationError("End port must be between 1 and 65535.")

    if port_start > port_end:
        raise ValidationError("Start port must be less than or equal to end port.")

    port_count = port_end - port_start + 1
    if port_count > MAX_PORT_RANGE:
        raise ValidationError(
            f"Port range too large: {port_count} ports requested, "
            f"maximum allowed is {MAX_PORT_RANGE}."
        )

    return port_start, port_end
