"""Tests for crawlkit.models — data classes, flag constants, attribution builders."""

import unittest

from crawlkit.models import (
    Flag,
    ParsedStory,
    build_record,
    build_attribution_block,
    normalize_terms,
    strip_attribution,
    ATTRIBUTION_SEPARATOR,
)


class ModelsTests(unittest.TestCase):
    def test_flag_constants_exist(self):
        self.assertTrue(hasattr(Flag, "EMPTY_BODY"))
        self.assertTrue(hasattr(Flag, "MISSING_TITLE"))
        self.assertTrue(hasattr(Flag, "MISSING_CANONICAL"))

    def test_normalize_terms_dedupes_and_lowers(self):
        terms = ["Femboy", " FEMBOY ", "femboy", "Stories", "story", ""]
        out = normalize_terms(terms)
        self.assertIn("femboy", out)
        self.assertNotIn("stories", out)
        self.assertNotIn("story", out)
        for t in out:
            self.assertEqual(t, t.lower())

    def test_build_attribution_block_includes_separator(self):
        block = build_attribution_block(
            source_url="https://example.com/x",
            site_name="Ex",
            site_host="example.com",
            author_name=None,
            author_url=None,
            published_at=None,
            categories=[],
            tags=[],
            license_note="public domain",
            archived_at="2026-08-19T00:00:00Z",
        )
        self.assertIn("Source URL:", block)
        self.assertIn("not listed", block)
        self.assertIn("public domain", block)

    def test_strip_attribution_cuts_at_separator(self):
        body = f"first paragraph{ATTRIBUTION_SEPARATOR}\nattribution stuff"
        self.assertEqual(strip_attribution(body), "first paragraph")
        self.assertEqual(strip_attribution("just text"), "just text")

    def test_build_record_flags_empty_body(self):
        parsed = ParsedStory(
            source_url="https://x",
            dedup_key="x",
            canonical_url="https://x",
            body_paragraphs=[],
        )
        rec = build_record(parsed, site_id="t", site_name="T", site_host="t.test",
                           license_note="pd", adapter_version="1.0")
        self.assertIn(Flag.EMPTY_BODY, rec.flags)
        self.assertFalse(rec.is_complete)

    def test_build_record_flags_short_body(self):
        parsed = ParsedStory(
            source_url="https://x", dedup_key="x", canonical_url="https://x",
            body_paragraphs=["hi"],
        )
        rec = build_record(parsed, site_id="t", site_name="T", site_host="t.test",
                           license_note="pd", adapter_version="1.0")
        self.assertIn(Flag.SHORT_BODY, rec.flags)

    def test_build_record_complete_when_clean(self):
        parsed = ParsedStory(
            source_url="https://x", dedup_key="x", canonical_url="https://x",
            title="A title", author_name="Alice",
            published_at="2026-08-19T00:00:00Z",
            tags=["femboy"], categories=["romance"],
            body_paragraphs=["first paragraph here", "second paragraph here"],
        )
        rec = build_record(parsed, site_id="t", site_name="T", site_host="t.test",
                           license_note="pd", adapter_version="1.0")
        self.assertTrue(rec.is_complete)
        self.assertNotIn(Flag.EMPTY_BODY, rec.flags)
        self.assertNotIn(Flag.MISSING_TITLE, rec.flags)


if __name__ == "__main__":
    unittest.main()
