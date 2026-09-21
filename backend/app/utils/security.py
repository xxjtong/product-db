"""SSRF prevention utilities."""
import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}

# 用户填写的链接（产品链接、附件外链）：只允许 http/https。
# 这些链接会被前端直接 window.open / <a href> 打开，`javascript:`、`data:` 之类
# 可执行协议就成了 XSS 跳板 —— 和 validate_url（服务端抓取用的 SSRF 防护）关注点不同，
# 所以单独一个函数，不拦内网 IP（用户填内网链接是正常需求）。
_USER_URL_SCHEMES = {"http", "https"}

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


def _resolve_host_ips(hostname: str) -> list:
    """Resolve a hostname to its IP addresses (empty list on failure)."""
    try:
        ips = []
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ip not in ips:
                ips.append(ip)
        return ips
    except socket.gaierror:
        return []


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

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        # Literal IP: validate directly
        return _is_ip_allowed(hostname)

    # Hostname: resolve NOW and block if any resolved IP is private/unallowed.
    # This closes the DNS-rebinding gap (e.g. 169.254.169.254.nip.io).
    resolved = _resolve_host_ips(hostname)
    if not resolved:
        return False
    return all(_is_ip_allowed(ip) for ip in resolved)


def is_safe_user_url(url: str) -> bool:
    """用户填写的链接是否安全（只允许 http/https 且必须带主机）。

    与 `validate_url` 的分工：那个用于「服务端按用户给的 URL 去抓取」的场景（SSRF 防护，
    还会拦内网 IP）；这个用于「用户存一个链接、前端打开它」的场景 —— 要防的是
    `javascript:`/`data:` 这类可执行协议（配合 window.open / <a href> 就是 XSS 跳板），
    而不能拦内网地址（用户填内网系统链接是正常需求）。
    """
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return False
    return parsed.scheme.lower() in _USER_URL_SCHEMES and bool(parsed.netloc)
