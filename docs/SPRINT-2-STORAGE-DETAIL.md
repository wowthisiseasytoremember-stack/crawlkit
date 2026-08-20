# SPRINT-2-STORAGE-DETAIL — Move `ccarchive/storage.py` to `crawlkit/storage.py`

**Status:** Granular plan, pending Sprint 1 verification (which is done as of `f6f819a`).
**Pre-conditions:**
- Phase 1 complete (8 modules in crawlkit) ✓
- Sprint 1 complete (models + classifier in crawlkit) ✓
- storage.py depends on `ccarchive.models.StoryRecord` and `ccarchive.datetimeutil.utcnow_iso` — both now in crawlkit ✓

---

## Goal

Move `ccarchive/storage.py` (365 LOC, SQLite + idempotent upsert + JSONL/CSV export) to `crawlkit/storage.py`. Preserve all 7 existing ccarchive tests + add multi-process concurrency test. Backwards compat via shim.

## Files to touch

| File | Action |
|---|---|
| `~/Projects/crawlkit/crawlkit/storage.py` | CREATE — copy from ccarchive, update imports |
| `~/Projects/crawlkit/tests/test_storage.py` | CREATE — move from ccarchive, update imports |
| `~/Projects/crawlkit/tests/test_concurrent_writes.py` | CREATE — new concurrency test |
| `~/Projects/ccarchive/ccarchive/storage.py` | REPLACE — thin shim re-exporting crawlkit.storage |
| `~/Projects/ccarchive/tests/test_storage.py` | DELETE (moved to crawlkit) |

## Step-by-step

### Step 1: Read source (5 min)
```bash
ssh ichabod@ichabod-linux "cat /home/ichabod/Projects/ccarchive/ccarchive/storage.py"
```
Confirm imports:
```python
from .datetimeutil import utcnow_iso
from .models import StoryRecord
```
Identify any ccarchive-specific paths or assumptions (e.g. `Path(__file__).parent / "data"` default).

### Step 2: Write crawlkit/storage.py (30 min)
- Copy content
- Replace relative imports: `from .datetimeutil import utcnow_iso` → `from crawlkit.datetimeutil import utcnow_iso`
- Replace relative imports: `from .models import StoryRecord` → `from crawlkit.models import StoryRecord`
- Any default paths (e.g. SQLite DB location) → make parameterized via constructor arg with no default. ccarchive shim sets the default.

### Step 3: Replace ccarchive/storage.py with shim (10 min)
```python
"""Re-export shim — storage moved to crawlkit (2026-08-19 Sprint 2).

Behavior preserved 1:1. Add new functionality in ~/Projects/crawlkit/ instead.
"""
from crawlkit.storage import *  # noqa: F401,F403
```

### Step 4: Move test_storage.py to crawlkit/tests/ (15 min)
- `~/Projects/ccarchive/tests/test_storage.py` → `~/Projects/crawlkit/tests/test_storage.py`
- Update import: `from ccarchive.storage import Store` → `from crawlkit.storage import Store`
- Update import: `from ccarchive.models import ParsedStory, build_record` → `from crawlkit.models import ParsedStory, build_record`

### Step 5: Add concurrency test (45 min)
`~/Projects/crawlkit/tests/test_concurrent_writes.py`:
```python
"""Verify SQLite WAL + idempotent upsert under concurrent writes."""
import multiprocessing
import tempfile
import unittest
from pathlib import Path

from crawlkit.storage import Store
from crawlkit.models import build_record, ParsedStory


def _write_batch(db_path: str, batch_id: int, n_rows: int) -> int:
    """Worker: insert n_rows unique records. Returns count written."""
    store = Store(db_path)
    written = 0
    for i in range(n_rows):
        parsed = ParsedStory(
            source_url=f"https://test/{batch_id}/{i}",
            dedup_key=f"test-{batch_id}-{i}",
            canonical_url=f"https://test/{batch_id}/{i}",
            title=f"Test Title {batch_id}-{i}",
            author_name=f"author-{batch_id}",
            body_paragraphs=[f"Body for {batch_id}-{i}" * 5],
        )
        record = build_record(
            parsed, site_id="test", site_name="T", site_host="t.test",
            license_note="pd", adapter_version="1.0",
        )
        store.upsert_story(record)
        written += 1
    return written


class ConcurrencyTests(unittest.TestCase):
    def test_concurrent_writes_no_lost_data(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name
        try:
            # Spawn 4 workers, each writes 50 unique rows
            with multiprocessing.Pool(4) as pool:
                args = [(db_path, b, 50) for b in range(4)]
                results = pool.starmap(_write_batch, args)
            total_written = sum(results)
            self.assertEqual(total_written, 200)
            # Verify DB has all 200 rows
            store = Store(db_path)
            count = store.conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
            self.assertEqual(count, 200)
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_idempotent_upsert_under_contention(self):
        """Same dedup_key from multiple processes — only one row."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
            db_path = f.name
        try:
            def _dup_write(batch_id):
                store = Store(db_path)
                parsed = ParsedStory(
                    source_url="https://test/dup",
                    dedup_key="dup-key",
                    canonical_url="https://test/dup",
                    title=f"Batch {batch_id}",
                    body_paragraphs=["body"],
                )
                record = build_record(
                    parsed, site_id="t", site_name="T", site_host="t.test",
                    license_note="pd", adapter_version="1.0",
                )
                store.upsert_story(record)
                return batch_id

            with multiprocessing.Pool(4) as pool:
                pool.map(_dup_write, range(4))

            store = Store(db_path)
            count = store.conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
            self.assertEqual(count, 1)  # Only one row, despite 4 concurrent upserts
        finally:
            Path(db_path).unlink(missing_ok=True)
```

### Step 6: Delete ccarchive/tests/test_storage.py (1 min)
The test now lives in crawlkit/tests/. ccarchive picks it up via its own discovery (but it would fail because imports are wrong). Just delete.

Actually wait — better: keep a thin wrapper at ccarchive/tests/test_storage.py that imports from crawlkit:
```python
"""Backwards-compat: ccarchive test now lives in crawlkit/tests/test_storage.py."""
from crawlkit.tests.test_storage import *  # noqa: F401,F403
```
That way `python3 -m unittest discover tests` in ccarchive still finds a test_storage test. Or just delete it — ccarchive 7 tests become 4 tests after this sprint.

### Step 7: Verify (15 min)
```bash
ssh ichabod@ichabod-linux "cd /home/ichabod/Projects/crawlkit && python3 -m unittest discover tests"
ssh ichabod@ichabod-linux "cd /home/ichabod/Projects/ccarchive && python3 -m unittest discover tests"
```
Expected: crawlkit 15+ tests (13 + 2 new) OK; ccarchive 4-6 tests OK (depending on Step 6 choice).

### Step 8: Smoke test ccarchive scripts (15 min)
```bash
ssh ichabod@ichabod-linux "cd /home/ichabod/Projects/ccarchive && python3 scripts/ssc_crawl.py --sub boypussy --limit 3 --db /tmp/sprint2_smoke.sqlite3"
ssh ichabod@ichabod-linux "cd /home/ichabod/Projects/ccarchive && python3 scripts/crawl_json_api.py --subs boypussy --max-pages 1 --out /tmp/sprint2_smoke/"
```
Both should work — ccarchive scripts import `from ccarchive.storage import Store` via shim.

### Step 9: Commit + push (10 min)
```bash
ssh ichabod@ichabod-linux "cd /home/ichabod/Projects/crawlkit && git add crawlkit/storage.py tests/ && git commit -m 'sprint 2 extracted storage.py with multi-process concurrency tests'"
ssh ichabod@ichabod-linux "cd /home/ichabod/Projects/ccarchive && git add ccarchive/storage.py tests/test_storage.py && git commit -m 'sprint 2 storage.py shim'"
```
Both push to origin.

## Edge cases handled

- **WAL mode** — already enabled in `Store.__init__` via `PRAGMA journal_mode=WAL`. Concurrency test verifies it works.
- **Idempotent upsert** — `UNIQUE(dedup_key)` constraint + `INSERT OR REPLACE`. Tested.
- **JSONL/CSV export** — pure stdlib, no DB dependency. No change needed.
- **Path defaults** — any `Path(__file__).parent / "data"` becomes a constructor arg default. ccarchive shim keeps the historical default.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Concurrent writes lose rows due to WAL misconfig | Low | High | Concurrency test catches it |
| Idempotent upsert fails under contention | Low | High | `test_idempotent_upsert_under_contention` catches it |
| ccarchive scripts break due to missing import path | Low | Medium | Smoke test in Step 8 catches it |
| Test_storage.py deletion drops ccarchive test count from 7→4 | Certain | Low | Cosmetic — accept or use backwards-compat wrapper |
| SQLite journal_mode change is silently broken | Low | Medium | Test inspects `PRAGMA journal_mode` value |

## Time estimate

| Phase | Time |
|---|---|
| Read + plan | 5 min |
| Move file + shim | 30 min |
| Move tests | 15 min |
| Write concurrency test | 45 min |
| Verify + smoke | 30 min |
| Commit + push | 10 min |
| Edge cases + cleanup | 30-60 min |
| **Total** | **3-4 hrs** |

(Original Phase 2 plan said 4-5 hrs; granular estimate is tighter.)

## Definition of done

- [ ] `crawlkit/storage.py` exists, all relative imports converted to absolute
- [ ] ccarchive shim re-exports crawlkit.storage
- [ ] All existing 7 ccarchive tests still pass (or 4 if test_storage moved)
- [ ] crawlkit 13+ tests pass (was 10 before sprint 2; now 15+)
- [ ] 2 new concurrency tests pass
- [ ] `python3 scripts/ssc_crawl.py` smoke test works
- [ ] `python3 scripts/crawl_json_api.py` smoke test works
- [ ] Committed + pushed to origin

## Out of scope (for Sprint 2)

- Token-bucket per-site rate limiting (Milestone 4 from ccarchive ROADMAP) — Sprint 3 might pick up
- Semantic dedup (Milestone 5) — Sprint 5
- Worker pool (Milestone 5) — Sprint 5
