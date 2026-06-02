"""SSRF prevention utilities."""
import ipaddress
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}

_BLOCKED_HOSTNAMES = {
    "169.254.169.254",
    "metadata.google.internal",
    "localhost",
    "0.0.0.0",
}

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_ip_allowed(ip_str: str) -> bool:
    """Check if an IP address is allowed (not in blocked private ranges)."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                return False
        return True
    except ValueError:
        return False


def validate_url(url: str) -> bool:
    """Validate URL scheme and block private/metadata hosts (SSRF prevention)."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False

    hostname = (parsed.hostname or "").lower()

    # Check blocked hostnames
    for blocked in _BLOCKED_HOSTNAMES:
        if hostname == blocked or hostname.endswith("." + blocked):
            return False

    # Check private/blocked IP ranges
    if not _is_ip_allowed(hostname):
        # If it's already an IP, block it. If it looks like a hostname (not an IP),
        # don't block here — DNS rebinding protection is handled by the transport layer.
        try:
            ipaddress.ip_address(hostname)
            return False  # literal IP in blocked range
        except ValueError:
            pass  # hostname, will be checked at connection time

    return True
