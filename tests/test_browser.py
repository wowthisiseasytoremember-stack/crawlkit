"""Tests for crawlkit.browser — mock Playwright, no live Chrome needed."""

import unittest
from unittest import mock

from crawlkit.browser import (
    BLOCKED_RESOURCE_TYPES,
    CDPSession,
    FetchError,
    FetchResult,
    RobotsDisallowed,
)
from crawlkit.pacing import Pacer
from crawlkit.robots import RobotsGate


class FakeLocator:
    def __init__(self, visible: bool = True):
        self.visible = visible
        self._clicked = False

    @property
    def first(self):
        return self

    async def count(self) -> int:
        return 1 if self.visible else 0

    async def is_visible(self) -> bool:
        return self.visible

    async def click(self, timeout: int = 0) -> None:
        self._clicked = True


class FakePage:
    def __init__(self, *, visible_consent: bool = True):
        self._visible_consent = visible_consent
        self._closed = False
        self.url = "https://example.com/final"
        self.content_html = "<html><body>ok</body></html>"
        self.consent_clicks = 0

    def is_closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self._closed = True

    async def goto(self, url, wait_until="domcontentloaded", timeout=0):
        class _Resp:
            status = 200

        return _Resp()

    async def content(self) -> str:
        return self.content_html

    async def wait_for_timeout(self, ms: int) -> None:
        return None

    async def wait_for_selector(self, sel, timeout=0, state="attached") -> None:
        return None

    def locator(self, selector):
        loc = FakeLocator(visible=self._visible_consent)

        async def _click_and_count(timeout=0):
            loc._clicked = True
            self.consent_clicks += 1

        loc.click = _click_and_count
        return _First(loc)

    def get_by_role(self, role, name=None, exact=False):
        loc = FakeLocator(visible=self._visible_consent)

        async def _click_and_count(timeout=0):
            loc._clicked = True
            self.consent_clicks += 1

        loc.click = _click_and_count
        return _First(loc)


class _First:
    """Wraps a FakeLocator so `.first` behaves like Playwright's."""

    def __init__(self, loc: FakeLocator):
        self._loc = loc

    @property
    def first(self):
        return self._loc


class BrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_returns_result(self):
        session = CDPSession(
            pacer=Pacer(0.0),
            robots=RobotsGate(enabled=False),
            settle_ms=0,
            max_retries=1,
        )
        session._page = FakePage()
        res = await session.fetch("https://example.com/a", wait_for=["body"])
        self.assertIsInstance(res, FetchResult)
        self.assertEqual(res.url, "https://example.com/a")
        self.assertEqual(res.status, 200)
        self.assertIn("<html>", res.html)

    async def test_fetch_raises_robots_disallowed(self):
        gate = mock.Mock()
        gate.allowed.return_value = False
        session = CDPSession(pacer=Pacer(0.0), robots=gate)
        with self.assertRaises(RobotsDisallowed):
            await session.fetch("https://example.com/blocked")

    async def test_fetch_retries_then_raises(self):
        session = CDPSession(
            pacer=Pacer(0.0),
            robots=RobotsGate(enabled=False),
            settle_ms=0,
            max_retries=2,
        )

        class BoomPage(FakePage):
            async def goto(self, url, wait_until="domcontentloaded", timeout=0):
                class _Resp:
                    status = 500

                return _Resp()

        session._page = BoomPage()
        # max_retries=2 → final exception is the generic re-wrap (status lost)
        with self.assertRaises(FetchError) as ctx:
            await session.fetch("https://example.com/boom")
        self.assertIn("failed on", str(ctx.exception))

    async def test_fetch_retries_then_succeeds(self):
        session = CDPSession(
            pacer=Pacer(0.0),
            robots=RobotsGate(enabled=False),
            settle_ms=0,
            max_retries=2,
        )

        class FlakyPage(FakePage):
            def __init__(self):
                super().__init__()
                self.calls = 0

            async def goto(self, url, wait_until="domcontentloaded", timeout=0):
                self.calls += 1

                class _Resp:
                    status = 429 if self.calls == 1 else 200

                return _Resp()

        flaky = FlakyPage()
        session._page = flaky
        res = await session.fetch("https://example.com/flaky")
        self.assertEqual(res.status, 200)
        self.assertEqual(flaky.calls, 2)

    async def test_fetch_raises_on_429(self):
        session = CDPSession(
            pacer=Pacer(0.0),
            robots=RobotsGate(enabled=False),
            settle_ms=0,
            max_retries=2,
        )

        class ThrottlePage(FakePage):
            async def goto(self, url, wait_until="domcontentloaded", timeout=0):
                class _Resp:
                    status = 429

                return _Resp()

        session._page = ThrottlePage()
        with self.assertRaises(FetchError) as ctx:
            await session.fetch("https://example.com/throttle")
        self.assertIn("failed on", str(ctx.exception))

    async def test_dismiss_interstitials_clicks_visible(self):
        session = CDPSession(pacer=Pacer(0.0), robots=RobotsGate(enabled=False))
        page = FakePage(visible_consent=True)
        session._page = page
        await session.dismiss_interstitials()
        self.assertGreater(page.consent_clicks, 0)

    async def test_dismiss_interstitials_noop_when_none_visible(self):
        session = CDPSession(pacer=Pacer(0.0), robots=RobotsGate(enabled=False))
        page = FakePage(visible_consent=False)
        session._page = page
        await session.dismiss_interstitials()
        self.assertEqual(page.consent_clicks, 0)

    async def test_page_property_raises_when_closed(self):
        session = CDPSession()
        session._page = FakePage()
        await session._page.close()
        with self.assertRaises(FetchError):
            _ = session.page

    async def test_route_filter_aborts_blocked_types(self):
        session = CDPSession()
        for rtype in BLOCKED_RESOURCE_TYPES:
            route = mock.AsyncMock()
            request = mock.Mock()
            request.resource_type = rtype
            await session._route_filter(route, request)
            route.abort.assert_awaited_once()
            route.continue_.assert_not_awaited()

        route = mock.AsyncMock()
        request = mock.Mock()
        request.resource_type = "document"
        await session._route_filter(route, request)
        route.continue_.assert_awaited_once()
        route.abort.assert_not_awaited()

    async def test_fetch_error_attributes(self):
        err = FetchError("boom", status=404, retryable=False)
        self.assertEqual(err.status, 404)
        self.assertFalse(err.retryable)
        err2 = FetchError("boom")
        self.assertIsNone(err2.status)
        self.assertTrue(err2.retryable)

    async def test_robots_disallowed_is_subclass(self):
        err = RobotsDisallowed("https://example.com/x")
        self.assertIsInstance(err, FetchError)
        self.assertFalse(err.retryable)


if __name__ == "__main__":
    unittest.main()
