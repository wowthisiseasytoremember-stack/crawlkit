# CHANGELOG

## 2026-08-19 — Phase 1 extracted from ccarchive

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
