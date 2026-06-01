"""
Custom template tags for the scanner app.
"""
from django import template

register = template.Library()

_WELL_KNOWN = {
    20: "FTP-Data", 21: "FTP", 22: "SSH", 23: "Telnet",
    25: "SMTP", 53: "DNS", 67: "DHCP", 68: "DHCP",
    69: "TFTP", 80: "HTTP", 110: "POP3", 119: "NNTP",
    123: "NTP", 135: "MSRPC", 139: "NetBIOS", 143: "IMAP",
    161: "SNMP", 194: "IRC", 389: "LDAP", 443: "HTTPS",
    445: "SMB", 465: "SMTPS", 514: "Syslog", 587: "SMTP-Sub",
    636: "LDAPS", 993: "IMAPS", 995: "POP3S",
    1080: "SOCKS", 1433: "MSSQL", 1521: "Oracle",
    2049: "NFS", 2181: "Zookeeper", 3306: "MySQL",
    3389: "RDP", 5432: "PostgreSQL", 5672: "AMQP",
    5900: "VNC", 6379: "Redis", 6443: "K8s-API",
    8080: "HTTP-Alt", 8443: "HTTPS-Alt", 8888: "Jupyter",
    9200: "Elasticsearch", 11211: "Memcached",
    27017: "MongoDB", 27018: "MongoDB", 50000: "DB2",
}


@register.filter
def well_known_service(port: int) -> str:
    """Return a human-readable service name for well-known ports."""
    try:
        return _WELL_KNOWN.get(int(port), "—")
    except (TypeError, ValueError):
        return "—"
