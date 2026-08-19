"""Adapter & Endpoint Health Monitor (Inspired by FloraTrack health_monitor.py)."""

from __future__ import annotations

import logging
from typing import Any

from .adapters import REGISTRY
from .browser import CDPSession
from .robots import RobotsGate

log = logging.getLogger("ccarchive.health")


async def check_adapter_health(session: CDPSession, site_id: str) -> dict[str, Any]:
    if site_id not in REGISTRY:
        return {
            "site": site_id,
            "status": "FAIL",
            "reason": f"Adapter {site_id} not registered",
        }

    adapter = REGISTRY[site_id]()
    start_url = (
        adapter.default_start_urls[0]
        if adapter.default_start_urls
        else adapter.base_url
    )

    try:
        # If adapter has robots disabled, override the session's robots gate
        if getattr(adapter, "robots_disabled", False):
            session.robots = RobotsGate(enabled=False)

        res = await session.fetch(
            start_url, wait_for=list(adapter.listing_ready_selectors)
        )
        if res.status and res.status >= 400:
            return {
                "site": site_id,
                "status": "FAIL",
                "http_status": res.status,
                "url": start_url,
            }

        # Check basic DOM integrity
        from .textutil import soup_of

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


async def run_health_checks(cdp_url: str) -> list[dict[str, Any]]:
    results = []
    async with CDPSession(endpoint=cdp_url) as session:
        for site_id in REGISTRY.keys():
            res = await check_adapter_health(session, site_id)
            results.append(res)
    return results
