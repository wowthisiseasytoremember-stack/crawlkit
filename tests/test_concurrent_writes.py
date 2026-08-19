"""Multi-process concurrency tests for crawlkit.storage.

SQLite WAL mode + INSERT OR REPLACE pattern should give us:
- No lost writes under concurrent access
- Idempotent upsert (same dedup_key from multiple processes)
- No corruption under contention
"""

import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path

from crawlkit.models import ParsedStory, build_record
from crawlkit.storage import Store


def _write_unique_rows(db_path: str, batch_id: int, n_rows: int) -> int:
    """Worker: write n_rows unique records. Returns count written."""
    store = Store(db_path, init_schema=False)
    written = 0
    for i in range(n_rows):
        parsed = ParsedStory(
            source_url=f"https://test/{batch_id}/{i}",
            dedup_key=f"test-{batch_id}-{i}",
            canonical_url=f"https://test/{batch_id}/{i}",
            title=f"Title {batch_id}-{i}",
            author_name=f"author-{batch_id}",
            body_paragraphs=[f"Body content for {batch_id}-{i} " * 5],
        )
        record = build_record(
            parsed, site_id="test", site_name="T", site_host="t.test",
            license_note="pd", adapter_version="1.0",
        )
        store.upsert_story(record)
        written += 1
    store.close()
    return written


def _write_same_dedup_key(db_path: str, batch_id: int) -> int:
    """Worker: write 1 record with the same dedup_key. Returns 1 if wrote."""
    store = Store(db_path, init_schema=False)
    parsed = ParsedStory(
        source_url="https://test/dup",
        dedup_key="dup-key",
        canonical_url="https://test/dup",
        title=f"Batch {batch_id}",
        body_paragraphs=["shared body"],
    )
    record = build_record(
        parsed, site_id="t", site_name="T", site_host="t.test",
        license_note="pd", adapter_version="1.0",
    )
    store.upsert_story(record)
    store.close()
    return 1


class ConcurrencyTests(unittest.TestCase):
    def test_concurrent_writes_no_lost_data(self):
        """4 processes × 50 unique rows each = 200 rows total. No lost writes."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name
        try:
            # Initialize schema once before spawning workers (avoid SCHEMA contention)
            Store(db_path).close()
            with multiprocessing.Pool(4) as pool:
                args = [(db_path, b, 50) for b in range(4)]
                results = pool.starmap(_write_unique_rows, args)
            total_written = sum(results)
            self.assertEqual(total_written, 200)

            store = Store(db_path)
            count = store.conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
            store.close()
            self.assertEqual(count, 200)
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_idempotent_upsert_under_contention(self):
        """4 processes write same dedup_key — only one row in DB."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name
        try:
            # Initialize schema once before spawning workers
            Store(db_path).close()
            with multiprocessing.Pool(4) as pool:
                pool.starmap(_write_same_dedup_key, [(db_path, b) for b in range(4)])

            store = Store(db_path)
            count = store.conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
            store.close()
            self.assertEqual(count, 1)
        finally:
            Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
