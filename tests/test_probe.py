"""Tests for crawlkit.probe — offline HTML-string probe, no live Chrome."""

import io
import unittest
from contextlib import redirect_stdout

from crawlkit.browser import FetchResult
from crawlkit.models import ParsedStory
from crawlkit.probe import probe_url


class FakeAdapter:
    site_id = "fake"
    display_name = "Fake Site"
    base_host = "fake.example"
    base_url = "https://fake.example"
    license_note = "Test license"
    adapter_version = "9.9.9"

    async def fetch_story(self, fetch, url):
        return await fetch(url)

    async def parse_story(self, result):
        return ParsedStory(
            source_url=result.final_url or result.url,
            dedup_key="https://fake.example/s/abc",
            canonical_url=result.final_url or result.url,
            external_id="abc",
            title="Test Story",
            author_name="Test Author",
            author_url="https://fake.example/u/test",
            published_at="2026-08-01T00:00:00+00:00",
            published_at_raw="Aug 1, 2026",
            tags=["trans", "femboy"],
            categories=["Transgender"],
            body_paragraphs=[
                "This is the first paragraph of the story body, long enough to extract.",
                "This is a second paragraph of the story body.",
            ],
            source_keywords=["trans", "story"],
            source_description="A test story.",
            primary_niche="niche_relational_romance",
            target_funnel="weekly_syndicate_newsletter",
            recommended_affiliate="niche_dating_networks",
            seo_slug="test-story",
            extra={"selectors_used": {"title": "h1", "body": "[itemprop='articleBody']"}},
            http_status=200,
        )


class FakeSession:
    def __init__(self, html: str, final_url: str = "https://fake.example/s/abc"):
        self._html = html
        self._final_url = final_url

    async def fetch(self, url, **kwargs):
        return FetchResult(
            url=url, final_url=self._final_url, status=200, html=self._html
        )


class ProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_extracts_fields(self):
        adapter = FakeAdapter()
        session = FakeSession("<html><body><h1>Test Story</h1></body></html>")
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = await probe_url(session, adapter, "https://fake.example/s/abc")
        out = buf.getvalue()

        self.assertEqual(result["source_site"], "fake")
        self.assertIn("Test Story", out)
        self.assertIn("Test Author", out)
        self.assertIn("niche_relational_romance", out)
        self.assertIn("weekly_syndicate_newsletter", out)
        self.assertIn("Test license", out)
        self.assertIn("PROBING: https://fake.example/s/abc on adapter fake", out)

    async def test_probe_tolerates_missing_author(self):
        adapter = FakeAdapter()

        async def parse_missing_author(result):
            parsed = await FakeAdapter.parse_story(adapter, result)
            parsed.author_name = None
            parsed.author_url = None
            return parsed

        adapter.parse_story = parse_missing_author
        session = FakeSession("<html><body></body></html>")
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = await probe_url(session, adapter, "https://fake.example/s/abc")
        self.assertEqual(result["source_site"], "fake")
        self.assertIn("None", buf.getvalue())  # author shows as None

    async def test_probe_saves_html_when_requested(self):
        import tempfile
        import os

        adapter = FakeAdapter()
        session = FakeSession("<html><body>saved</body></html>")
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
        tmp.close()
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                await probe_url(
                    session, adapter, "https://fake.example/s/abc", save_html=tmp.name
                )
            self.assertIn("Saved raw HTML", buf.getvalue())
            with open(tmp.name, encoding="utf-8") as f:
                self.assertIn("saved", f.read())
        finally:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
