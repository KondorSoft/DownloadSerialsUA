from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit, urlunsplit


PAGE_HOSTS = {"uakino.best": "UAKINO", "uafix.net": "UAFLIX"}
MEDIA_ROOTS = ("ashdi.vip", "zetvideo.net")


@dataclass(frozen=True)
class SourceUrl:
    site: str
    canonical_url: str


def _host_allowed(host: str, roots: tuple[str, ...] | set[str]) -> bool:
    return any(host == root or host.endswith("." + root) for root in roots)


def validate_url(raw: str, *, kind: str) -> str:
    parts = urlsplit(raw.strip())
    host = (parts.hostname or "").lower().rstrip(".")
    allowed_schemes = ("https",) if kind == "page" else ("https", "http")
    allowed_ports = (None, 443) if kind == "page" else (None, 80, 443)
    if parts.scheme not in allowed_schemes or not host or parts.username or parts.password or parts.port not in allowed_ports:
        raise ValueError("Потрібне HTTPS-посилання на підтримуваний сайт.")
    try:
        ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP-адреси не підтримуються.")
    roots = PAGE_HOSTS if kind == "page" else MEDIA_ROOTS
    if not _host_allowed(host, roots):
        raise ValueError("Цей сайт поки не підтримується.")
    return urlunsplit((parts.scheme, host, parts.path or "/", parts.query, ""))


def normalize_source_url(raw: str) -> SourceUrl:
    url = validate_url(raw, kind="page")
    host = urlsplit(url).hostname or ""
    site = next(value for root, value in PAGE_HOSTS.items() if _host_allowed(host, {root}))
    return SourceUrl(site=site, canonical_url=url)
