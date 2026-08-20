"""CDP attachment to an already-running headed Chrome + page fetching."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from playwright.async_api import Page, async_playwright

from crawlkit.pacing import Pacer
from crawlkit.robots import RobotsGate
from crawlkit.urlutil import host_of

log = logging.getLogger("crawlkit.browser")

__all__ = [
    "BLOCKED_RESOURCE_TYPES",
    "CONSENT_TEXTS",
    "CONSENT_SELECTORS",
    "FetchError",
    "FetchResult",
    "RobotsDisallowed",
    "CDPSession",
]

BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}

CONSENT_TEXTS = [
    "I am over 18",
    "I'm over 18",
    "Enter",
    "Continue",
    "Agree",
    "I Agree",
    "Accept",
    "Accept all",
    "AGREE",
    "Yes, I am 18 or older",
    "Enter Site",
]
CONSENT_SELECTORS = [
    "#age-verification button",
    ".age-gate button",
    "#consent button",
    "button#accept",
    "button.accept",
    "a.enter",
    "#disclaimer a.btn",
]


class FetchError(RuntimeError):
    def __init__(
        self, message: str, *, status: int | None = None, retryable: bool = True
    ):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class RobotsDisallowed(FetchError):
    def __init__(self, url: str):
        super().__init__(f"robots.txt disallows {url}", retryable=False)


@dataclass(slots=True)
class FetchResult:
    url: str
    final_url: str
    status: int | None
    html: str
    from_cache: bool = False


class CDPSession:
    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:9222",
        *,
        pacer: Pacer | None = None,
        robots: RobotsGate | None = None,
        new_context: bool = False,
        block_media: bool = True,
        nav_timeout_ms: int = 45_000,
        settle_ms: int = 350,
        max_retries: int = 3,
    ):
        self.endpoint = endpoint
        self.pacer = pacer or Pacer()
        self.robots = robots or RobotsGate(enabled=True)
        self.new_context = new_context
        self.block_media = block_media
        self.nav_timeout_ms = nav_timeout_ms
        self.settle_ms = settle_ms
        self.max_retries = max_retries

        self._pw = None
        self._browser = None
        self._context = None
        self._page: Page | None = None
        self._owns_context = False
        self._closed = False

    async def __aenter__(self) -> CDPSession:
        self._pw = await async_playwright().start()
        log.info("connecting to Chrome CDP endpoint at %s", self.endpoint)
        try:
            self._browser = await self._pw.chromium.connect_over_cdp(self.endpoint)
        except Exception as exc:
            await self._pw.stop()
            raise FetchError(
                f"could not attach to CDP endpoint {self.endpoint}: {exc}",
                retryable=False,
            ) from exc

        contexts = self._browser.contexts
        if self.new_context or not contexts:
            self._context = await self._browser.new_context()
            self._owns_context = True
        else:
            self._context = contexts[0]

        self._context.set_default_timeout(self.nav_timeout_ms)
        self._context.set_default_navigation_timeout(self.nav_timeout_ms)

        self._page = await self._context.new_page()
        if self.block_media:
            await self._page.route("**/*", self._route_filter)
        log.info("CDP scraper tab ready")
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
            if self._owns_context and self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
        except Exception as exc:
            log.debug("error during CDP teardown: %s", exc)
        finally:
            if self._pw:
                await self._pw.stop()

    async def _route_filter(self, route, request) -> None:
        if request.resource_type in BLOCKED_RESOURCE_TYPES:
            await route.abort()
        else:
            await route.continue_()

    @property
    def page(self) -> Page:
        if self._page is None or self._page.is_closed():
            raise FetchError("scraper page is not available", retryable=False)
        return self._page

    async def dismiss_interstitials(self) -> None:
        page = self.page
        for sel in CONSENT_SELECTORS:
            try:
                loc = page.locator(sel).first
                if await loc.count() and await loc.is_visible():
                    await loc.click(timeout=2000)
                    await page.wait_for_timeout(500)
                    return
            except Exception:
                continue
        for text in CONSENT_TEXTS:
            try:
                loc = page.get_by_role("button", name=text, exact=False).first
                if await loc.count() and await loc.is_visible():
                    await loc.click(timeout=2000)
                    await page.wait_for_timeout(500)
                    return
            except Exception:
                continue

    async def warmup(self, url: str) -> None:
        try:
            await self.page.goto(
                url, wait_until="domcontentloaded", timeout=self.nav_timeout_ms
            )
            await self.dismiss_interstitials()
        except Exception as exc:
            log.warning("warmup failed for %s: %s", url, exc)

    async def fetch(
        self,
        url: str,
        *,
        wait_for: list[str] | None = None,
        wait_until: str = "domcontentloaded",
    ) -> FetchResult:
        if not self.robots.allowed(url):
            raise RobotsDisallowed(url)

        host = host_of(url)
        last_exc = None

        for attempt in range(1, self.max_retries + 1):
            await self.pacer.wait(host)
            try:
                page = self.page
                resp = await page.goto(
                    url, wait_until=wait_until, timeout=self.nav_timeout_ms
                )
                status = resp.status if resp else None

                if status is not None and status >= 400:
                    if status in (429,) or status >= 500:
                        self.pacer.penalize(host, 5.0 * attempt)
                    raise FetchError(
                        f"HTTP {status} for {url}",
                        status=status,
                        retryable=(status in (408, 425, 429) or status >= 500),
                    )

                await self.dismiss_interstitials()

                if wait_for:
                    try:
                        await page.wait_for_selector(
                            ", ".join(wait_for), timeout=8000, state="attached"
                        )
                    except Exception:
                        pass

                if self.settle_ms:
                    await page.wait_for_timeout(self.settle_ms)

                html = await page.content()
                final_url = page.url
                self.pacer.relax(host)
                return FetchResult(
                    url=url, final_url=final_url, status=status, html=html
                )

            except RobotsDisallowed:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    break
                await asyncio.sleep(2.0**attempt)

        raise FetchError(f"failed on {url}: {last_exc}", retryable=False)
