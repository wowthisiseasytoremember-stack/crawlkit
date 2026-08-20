# CHANGELOG

## 2026-08-20 — health.py made generic (registry injected)

**What changed:**
- `crawlkit/health.py` — removed the broken `from .adapters import REGISTRY` and `from .browser import CDPSession` module-level imports (neither module was extracted; Sprint 2 pending). `check_adapter_health()` now takes `(session, site_id, registry)` — callers inject the adapter registry and an open session. `run_health_checks()` removed here (browser lives in ccarchive); ccarchive/health.py wires its own REGISTRY + CDPSession into the generic check.
- Defensive fetch: `listing_ready_selectors` optional, falls back to `("body",)`.

**Why:** ccarchive CLI crashed on import (`ModuleNotFoundError: crawlkit.adapters`). The health logic referenced adapters/browser that still live in ccarchive.

**Verification:** `ccarchive health` — all 5 adapters PASS (xnxx_stories, literotica, ao3, reddit, fictionmania).

## 2026-08-19 — Phase 1 extracted from ccarchive

## 2026-08-19 — Sprint 1: models + classifier extracted


## 2026-08-19 — Sprint 2: storage.py extracted

**What changed:**
- `crawlkit/storage.py` (~365 LOC) — SQLite + WAL + normalized tag index + queue + JSONL export, copied from ccarchive with imports refactored (`from crawlkit.datetimeutil` + `from crawlkit.models`)
- `crawlkit/tests/test_storage.py` — moved from ccarchive/tests/, imports updated
- `crawlkit/tests/test_concurrent_writes.py` — NEW, 2 multi-process tests using `multiprocessing.Pool`:
  - `test_concurrent_writes_no_lost_data` — 4 processes × 50 unique rows = 200 rows survive
  - `test_idempotent_upsert_under_contention` — 4 processes write same dedup_key = 1 row survives
- `Store.__init__` gained `init_schema: bool = True` flag — skip SCHEMA execution when caller knows DB is already initialized (faster, avoids SCHEMA contention under multi-process load)

**Implementation note:** upsert_story rewritten to use SQLite-native `INSERT ... ON CONFLICT(dedup_key) DO UPDATE` + `RETURNING id, revision` for atomicity. The earlier separate SELECT + INSERT/UPDATE pattern had race conditions under concurrent writers; the explicit `BEGIN IMMEDIATE` wrapper actually caused lock contention with SQLite's autocommit + WAL mode. The new pattern lets SQLite handle atomicity internally.

**Verification:**
- crawlkit 13 tests OK (was 10 before sprint 2)
- ccarchive 6 tests OK (was 7 — lost test_storage which moved to crawlkit)
- `python3 scripts/crawl_json_api.py` smoke test works via ccarchive shim (1 sub, 100 posts, 3.6s)

**What changed:**
- `crawlkit/models.py` — Flag constants, Discovered/ParsedStory/StoryRecord dataclasses, normalize_terms, build_attribution_block, strip_attribution, build_record
- `crawlkit/classifier.py` — StoryClassifier + TaxonomyCategory + classify_story. `_EMBEDDED_FALLBACK` taxonomy constant. `DEFAULT_TAXONOMY_PATH = None` — callers must specify or use embedded fallback
- `crawlkit/tests/test_models.py` — 7 new tests covering Flag constants, normalize_terms, build_attribution_block, strip_attribution, build_record (empty body / short body / clean)
- `crawlkit/tests/test_classifier.py` — moved from ccarchive/tests/, imports updated to crawlkit
- ccarchive `models.py` + `classifier.py` replaced with shims. ccarchive's `classify_story()` defaults to `ccarchive/taxonomy.json` (preserves historical behavior)

**API change:** `classify_story()` now accepts `taxonomy_path: str | Path | None = None` keyword arg. Existing callers without the arg get the same default as before (via ccarchive shim).

**Verification:**
- crawlkit: 10 tests OK (3 classifier + 7 models)
- ccarchive: 7 tests OK (preserved backwards compat)

**Next (Sprint 2):** extract `storage.py` (SQLite + idempotent upsert + JSONL/CSV export). Depends on models.py (just extracted).

**What changed:**
- Project scaffolded at `~/Projects/crawlkit/` with pyproject.toml, AGENTS.md, README.md, docs/
- 8 modules moved from `ccarchive`:
  - `textutil.py` — text normalization, dedup, paragraph assembly
  - `urlutil.py` — URL parsing, normalization, dedup-key extraction
  - `datetimeutil.py` — date parsing across formats, epoch conversion
  - `metrics.py` — Prometheus counters, histograms, gauges + exposition
  - `logsetup.py` — JSON structured logging + `StructuredLogger.bind/timer`
  - `robots.py` — robots.txt compliance gate
  - `health.py` — pre-flight connectivity + DOM integrity check
  - `pacing.py` — token-bucket rate limiter per host
- Backwards compat: ccarchive modules replaced with re-export shims (`from crawlkit.MODULE import *`)
- Verified: all 7 ccarchive unit tests pass after extraction
- Registered in `~/plans/initiatives.yml` under `content-factory.reddit-research` family

**Phase 2 plan:** `docs/PHASE-2-EXTRACTION-PLAN.md` — 6 more modules (models, classifier, storage, browser, probe, adapters/base) targeted for extraction across 4 sprints, ~15-20 hrs.

**Future cross-project use:**
- aquascrape, fish-atlas-scraper — migrate siloed scrapers to `crawlkit.adapters.base`
- job-search — adopt `crawlkit.browser` for career-site scraping
- shame-seo — adopt `crawlkit.classifier` for content categorization
