# CHANGELOG

## 2026-08-19 — Phase 1 extracted from ccarchive

## 2026-08-19 — Sprint 1: models + classifier extracted

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
