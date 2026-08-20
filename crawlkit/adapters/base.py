"""Base interfaces for Source Adapters."""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any
from urllib.parse import urljoin

from crawlkit.browser import FetchResult
from crawlkit.models import Discovered, ParsedStory
from crawlkit.textutil import clean_inline, soup_of
from crawlkit.urlutil import normalize_url, registrable_match

log = logging.getLogger("crawlkit.adapters.base")

Fetcher = Callable[..., Coroutine[Any, Any, FetchResult]]


class SourceAdapter(ABC):
    site_id: str
    display_name: str
    base_url: str
    base_host: str
    adapter_version: str = "1.0.0"
    language: str = "en"
    license_note: str = ""
    default_start_urls: tuple[str, ...] = ()
    request_delay: float = 2.0

    def normalize(self, url: str) -> str:
        return normalize_url(url)

    def dedup_key(self, url: str) -> str:
        return self.normalize(url)

    def external_id(self, url: str) -> str | None:
        return None

    @abstractmethod
    def discover(
        self,
        fetch: Fetcher,
        *,
        start_urls: list[str] | None = None,
        max_pages: int = 100,
        max_depth: int = 3,
    ) -> AsyncIterator[Discovered]: ...

    @abstractmethod
    async def fetch_story(self, fetch: Fetcher, url: str) -> FetchResult: ...

    @abstractmethod
    async def parse_story(self, result: FetchResult) -> ParsedStory: ...


class PatternCrawlAdapter(SourceAdapter):
    story_url_re: re.Pattern
    listing_url_res: tuple[re.Pattern, ...] = ()
    listing_ready_selectors: tuple[str, ...] = ()
    story_ready_selectors: tuple[str, ...] = ()

    def is_story_url(self, url: str) -> bool:
        return bool(self.story_url_re.search(url))

    def is_listing_url(self, url: str) -> bool:
        return any(bool(r.search(url)) for r in self.listing_url_res)

    async def discover(
        self,
        fetch: Fetcher,
        *,
        start_urls: list[str] | None = None,
        max_pages: int = 100,
        max_depth: int = 3,
    ) -> AsyncIterator[Discovered]:
        queue: list[tuple[str, int]] = [
            (self.normalize(u), 0) for u in (start_urls or self.default_start_urls)
        ]
        seen_listings: set[str] = set()
        seen_stories: set[str] = set()
        pages_fetched = 0

        while queue and pages_fetched < max_pages:
            url, depth = queue.pop(0)
            if url in seen_listings:
                continue
            seen_listings.add(url)
            pages_fetched += 1

            try:
                res = await fetch(url, wait_for=list(self.listing_ready_selectors))
            except Exception as exc:
                log.warning("discover: fetch failed for %s: %s", url, exc)
                continue

            soup = soup_of(res.html)
            for a in soup.find_all("a", href=True):
                href = (a.get("href") or "").strip()
                if not href or href.startswith(("#", "javascript:", "mailto:")):
                    continue
                abs_url = self.normalize(urljoin(res.final_url, href))
                if not registrable_match(abs_url, self.base_host):
                    continue

                if self.is_story_url(abs_url):
                    key = self.dedup_key(abs_url)
                    if key not in seen_stories:
                        seen_stories.add(key)
                        yield Discovered(
                            url=abs_url,
                            dedup_key=key,
                            listing_url=url,
                            hint_title=clean_inline(a.get_text()),
                        )
                elif (
                    depth < max_depth
                    and self.is_listing_url(abs_url)
                    and abs_url not in seen_listings
                ):
                    queue.append((abs_url, depth + 1))
