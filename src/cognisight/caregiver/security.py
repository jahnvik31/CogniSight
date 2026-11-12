"""Exact HTTPS LAN origins, behind exactly one local reverse proxy."""

import ipaddress
import re
from urllib.parse import urlsplit


def _authority(value):
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        return None
    try:
        authority = value
        try:
            if ipaddress.ip_address(value).version == 6:
                authority = "[" + value + "]"
        except ValueError:
            pass
        parsed = urlsplit("https://" + authority)
        if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            return None
        host = parsed.hostname
        port = parsed.port or 443
        if not host or host in ("0.0.0.0", "::") or "*" in host:
            return None
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", host):
                return None
        return host.lower(), port
    except (ValueError, TypeError):
        return None


def canonical_hosts(hosts):
    if not isinstance(hosts, (list, tuple)) or not hosts:
        raise ValueError("Explicit caregiver HTTPS hosts are required")
    result = {_authority(host) for host in hosts}
    if None in result:
        raise ValueError("Invalid caregiver host; use exact hostname/IP and optional port")
    return result


def allowed_request(host, origin, scheme, hosts, peer):
    if peer not in ("127.0.0.1", "::1") or scheme != "https":
        return False
    authority = _authority(host)
    if authority is None or authority not in hosts:
        return False
    if origin is None:
        return True
    try:
        parsed = urlsplit(origin)
        return (
            parsed.scheme == "https"
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and _authority(parsed.netloc) == authority
        )
    except (ValueError, TypeError):
        return False
