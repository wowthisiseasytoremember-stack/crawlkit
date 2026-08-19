import os
import tempfile
import unittest

from crawlkit.models import ParsedStory, build_record
from crawlkit.storage import Store


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.temp_db.close()
        self.store = Store(self.temp_db.name)

    def tearDown(self):
        self.store.close()
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_upsert_and_dedup(self):
        parsed = ParsedStory(
            source_url="https://www.sexstories.com/story/999/test-story",
            dedup_key="https://www.sexstories.com/story/999",
            title="Test Story",
            author_name="Alice",
            body_paragraphs=["Paragraph 1", "Paragraph 2"],
            tags=["femboy", "gfe"],
        )
        rec = build_record(
            parsed,
            site_id="xnxx_stories",
            site_name="XNXX Stories",
            site_host="sexstories.com",
            license_note="Test license",
            adapter_version="2.0.0",
        )
        outcome1 = self.store.upsert_story(rec)
        self.assertEqual(outcome1, "inserted")

        # Second upsert is unchanged
        outcome2 = self.store.upsert_story(rec)
        self.assertEqual(outcome2, "unchanged")

        # Verify query
        stories = list(self.store.iter_stories())
        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0]["title"], "Test Story")
        self.assertEqual(stories[0]["tags"], ["femboy", "gfe"])


if __name__ == "__main__":
    unittest.main()
