"""Adapter & Endpoint Health Monitor (Inspired by FloraTrack health_monitor.py).

Generic: callers inject the adapter registry and an open browser session.
ccarchive supplies both (browser + adapters still live there pending the
crawlkit Sprint 2 migration).
"""

from __future__ import annotations

import logging
from typing import Any

from .robots import RobotsGate
from .textutil import soup_of

log = logging.getLogger("crawlkit.health")


async def check_adapter_health(
    session: Any, site_id: str, registry: dict[str, Any]
) -> dict[str, Any]:
    """Run a single health check for site_id against the injected registry.

    session: an open CDPSession (or compatible fetcher) with `.fetch()`.
    registry: dict[str, type] mapping site_id -> adapter class.
    """
    if site_id not in registry:
        return {
            "site": site_id,
            "status": "FAIL",
            "reason": f"Adapter {site_id} not registered",
        }

    adapter = registry[site_id]()
    start_url = (
        adapter.default_start_urls[0]
        if adapter.default_start_urls
        else adapter.base_url
    )

    try:
        # If adapter has robots disabled, override the session's robots gate
        # for this check only, then restore — otherwise one adapter's setting
        # leaks to every subsequent adapter sharing the session.
        original_gate = getattr(session, "robots", None)
        try:
            if getattr(adapter, "robots_disabled", False):
                session.robots = RobotsGate(enabled=False)

            res = await session.fetch(
                start_url,
                wait_for=list(getattr(adapter, "listing_ready_selectors", ()) or ("body",)),
            )
        finally:
            if original_gate is not None:
                session.robots = original_gate

        if res.status and res.status >= 400:
            return {
                "site": site_id,
                "status": "FAIL",
                "http_status": res.status,
                "url": start_url,
            }

        soup = soup_of(res.html)
        links = soup.find_all("a", href=True)
        story_links = (
            [l for l in links if adapter.is_story_url(l["href"])]
            if hasattr(adapter, "is_story_url")
            else []
        )

        return {
            "site": site_id,
            "status": "PASS",
            "url": start_url,
            "http_status": res.status or 200,
            "html_bytes": len(res.html),
            "story_links_found": len(story_links),
        }
    except Exception as exc:
        return {"site": site_id, "status": "FAIL", "reason": str(exc), "url": start_url}
