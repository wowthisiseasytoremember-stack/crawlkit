"""Live selector diagnostic tool."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from crawlkit.adapters.base import SourceAdapter
from crawlkit.browser import CDPSession
from crawlkit.models import build_record
from crawlkit.textutil import soup_of

log = logging.getLogger("crawlkit.probe")


async def probe_url(
    session: CDPSession,
    adapter: SourceAdapter,
    url: str,
    *,
    save_html: str | None = None,
) -> dict:
    print(f"\n=== PROBING: {url} on adapter {adapter.site_id} ===")
    res = await adapter.fetch_story(session.fetch, url)
    print(
        f"HTTP Status: {res.status} | Final URL: {res.final_url} | HTML Size: {len(res.html)} bytes"
    )

    if save_html:
        Path(save_html).write_text(res.html, encoding="utf-8")
        print(f"Saved raw HTML to {save_html}")

    soup = soup_of(res.html)
    parsed = await adapter.parse_story(res)
    rec = build_record(
        parsed,
        site_id=adapter.site_id,
        site_name=adapter.display_name,
        site_host=adapter.base_host,
        license_note=adapter.license_note,
        adapter_version=adapter.adapter_version,
    )

    print("\n--- EXTRACTED FIELDS ---")
    print(f"Title:         {rec.title}")
    print(f"Author:        {rec.author_name} ({rec.author_url})")
    print(f"Published:     {rec.published_at} (raw: {rec.published_at_raw})")
    print(f"Categories:    {rec.categories}")
    print(f"Tags:          {rec.tags}")
    print(f"Keywords:      {rec.source_keywords}")
    print(f"Paragraphs:    {rec.paragraph_count}")
    print(f"Word Count:    {rec.word_count}")
    print(f"Content Hash:  {rec.content_hash}")
    print(f"Primary Niche: {rec.primary_niche}")
    print(f"Target Funnel: {rec.target_funnel}")
    print(f"Affiliate:     {rec.recommended_affiliate}")
    print(f"SEO Slug:      {rec.seo_slug}")
    print(f"Flags:         {rec.flags}")
    print(f"Selectors:     {json.dumps(rec.extra.get('selectors_used', {}), indent=2)}")

    print("\n--- BODY SAMPLE (First 2 Paragraphs) ---")
    pars = [p for p in rec.body_text.split("\n\n") if p.strip()]
    for i, p in enumerate(pars[:2], 1):
        print(f"[{i}] {p[:180]}...")

    print("\n--- ATTRIBUTION BLOCK ---")
    print(rec.attribution_block)
    return rec.to_dict()
