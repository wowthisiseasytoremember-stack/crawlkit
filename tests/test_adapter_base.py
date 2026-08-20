"""Tests for crawlkit.adapters.base — abstract contract + BFS discovery."""

import asyncio
import unittest
from urllib.parse import urljoin

from crawlkit.adapters.base import PatternCrawlAdapter, SourceAdapter
from crawlkit.browser import FetchResult


def make_fetch(html_map: dict[str, str], final_urls: dict[str, str] | None = None):
    """Build an async Fetcher that returns crafted HTML per URL."""

    async def fetch(url, **kwargs):
        html = html_map.get(url, "<html></html>")
        final = (final_urls or {}).get(url, url)
        return FetchResult(url=url, final_url=final, status=200, html=html)

    return fetch


class DummyAdapter(PatternCrawlAdapter):
    site_id = "dummy"
    display_name = "Dummy"
    base_url = "https://dummy.example"
    base_host = "dummy.example"

    import re

    story_url_re = re.compile(r"^https?://[^/]+/story/[a-z0-9-]+/?$")
    listing_url_res = (
        re.compile(r"^https?://[^/]+/list/?$"),
        re.compile(r"^https?://[^/]+/category/[^/]+/?$"),
    )

    async def fetch_story(self, fetch, url):
        return await fetch(url)

    async def parse_story(self, result):
        return None  # not exercised in these tests


class SourceAdapterContractTests(unittest.TestCase):
    def test_source_adapter_is_abstract(self):
        with self.assertRaises(TypeError):
            SourceAdapter()

    def test_pattern_adapter_defaults(self):
        a = DummyAdapter()
        self.assertEqual(a.request_delay, 2.0)
        self.assertEqual(a.adapter_version, "1.0.0")
        self.assertEqual(a.language, "en")

    def test_is_story_url_routing(self):
        a = DummyAdapter()
        self.assertTrue(a.is_story_url("https://dummy.example/story/hello"))
        self.assertFalse(a.is_story_url("https://dummy.example/list"))

    def test_is_listing_url_routing(self):
        a = DummyAdapter()
        self.assertTrue(a.is_listing_url("https://dummy.example/list"))
        self.assertTrue(a.is_listing_url("https://dummy.example/category/foo"))
        self.assertFalse(a.is_listing_url("https://dummy.example/story/x"))

    def test_dedup_key_normalizes(self):
        a = DummyAdapter()
        self.assertEqual(
            a.dedup_key("https://dummy.example/story/x"),
            a.normalize("https://dummy.example/story/x"),
        )


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.adapter = DummyAdapter()

    async def test_discovers_story_links(self):
        listing = """
        <html><body>
          <a href="/story/one">One</a>
          <a href="/story/two">Two</a>
          <a href="/list">More</a>
        </body></html>
        """
        html_map = {
            "https://dummy.example/": listing,
            "https://dummy.example/list": listing,
        }
        found = []
        async for d in self.adapter.discover(
            make_fetch(html_map),
            start_urls=["https://dummy.example/"],
            max_pages=2,
            max_depth=2,
        ):
            found.append(d)
        urls = {d.url for d in found}
        self.assertIn("https://dummy.example/story/one", urls)
        self.assertIn("https://dummy.example/story/two", urls)

    async def test_dedups_by_story_key(self):
        listing = """
        <html><body>
          <a href="/story/one">One</a>
          <a href="/story/one?utm_source=newsletter">One tracked</a>
        </body></html>
        """
        html_map = {"https://dummy.example/": listing}
        found = []
        async for d in self.adapter.discover(
            make_fetch(html_map),
            start_urls=["https://dummy.example/"],
            max_pages=1,
            max_depth=0,
        ):
            found.append(d)
        # default normalize_url strips tracking params → same dedup_key
        self.assertEqual(len(found), 1)

    async def test_ignores_off_host_links(self):
        listing = """
        <html><body>
          <a href="https://evil.example/story/hijack">Hijack</a>
          <a href="/story/local">Local</a>
        </body></html>
        """
        html_map = {"https://dummy.example/": listing}
        found = []
        async for d in self.adapter.discover(
            make_fetch(html_map),
            start_urls=["https://dummy.example/"],
            max_pages=1,
            max_depth=0,
        ):
            found.append(d)
        urls = {d.url for d in found}
        self.assertNotIn("https://evil.example/story/hijack", urls)
        self.assertIn("https://dummy.example/story/local", urls)

    async def test_depth_limit_controls_listing_traversal(self):
        page1 = """
        <html><body>
          <a href="/category/a">Cat A</a>
          <a href="/story/s1">S1</a>
        </body></html>
        """
        page2 = """
        <html><body>
          <a href="/story/deep">Deep</a>
        </body></html>
        """
        html_map = {
            "https://dummy.example/": page1,
            "https://dummy.example/category/a": page2,
        }
        found = []
        # max_depth=0 → only the start page (depth 0) is crawled; /category/a
        # at depth 1 is not queued, so /story/deep is never discovered
        async for d in self.adapter.discover(
            make_fetch(html_map),
            start_urls=["https://dummy.example/"],
            max_pages=10,
            max_depth=0,
        ):
            found.append(d)
        urls = {d.url for d in found}
        self.assertIn("https://dummy.example/story/s1", urls)
        self.assertNotIn("https://dummy.example/story/deep", urls)

    async def test_max_pages_bounds_fetch_volume(self):
        listing = """
        <html><body>
          <a href="/list/2">Next</a>
        </body></html>
        """
        html_map = {
            "https://dummy.example/list": listing,
            "https://dummy.example/list/2": listing,
        }
        calls = []

        async def counting_fetch(url, **kwargs):
            calls.append(url)
            html = html_map.get(url, "<html></html>")
            return FetchResult(url=url, final_url=url, status=200, html=html)

        async for _ in self.adapter.discover(
            counting_fetch,
            start_urls=["https://dummy.example/list"],
            max_pages=1,
            max_depth=3,
        ):
            pass
        self.assertEqual(len(calls), 1)

    async def test_discover_tolerates_fetch_failure(self):
        async def failing_fetch(url, **kwargs):
            raise RuntimeError("boom")

        results = []
        async for d in self.adapter.discover(
            failing_fetch,
            start_urls=["https://dummy.example/list"],
            max_pages=2,
            max_depth=1,
        ):
            results.append(d)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
