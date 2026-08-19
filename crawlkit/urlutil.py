"""URL normalization helpers shared by every adapter."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAM_PREFIXES = ("utm_", "fbclid", "gclid", "mc_", "ref_", "_ga")
TRACKING_PARAMS = {"ref", "referrer", "source", "share", "from"}


def normalize_url(
    url: str, *, drop_query: bool = False, keep_params: set[str] | None = None
) -> str:
    """Canonicalize a URL for comparison and dedup."""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    if parts.port and not (
        (scheme == "http" and parts.port == 80)
        or (scheme == "https" and parts.port == 443)
    ):
        host = f"{host}:{parts.port}"

    path = parts.path or "/"

    query = ""
    if not drop_query and parts.query:
        kept = []
        for k, v in parse_qsl(parts.query, keep_blank_values=True):
            lk = k.lower()
            if keep_params is not None and lk not in keep_params:
                continue
            if lk in TRACKING_PARAMS or lk.startswith(TRACKING_PARAM_PREFIXES):
                continue
            kept.append((k, v))
        query = urlencode(sorted(kept))

    return urlunsplit((scheme, host, path, query, ""))


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def registrable_match(url: str, base_host: str) -> bool:
    h = host_of(url)
    return h == base_host or h.endswith("." + base_host)
