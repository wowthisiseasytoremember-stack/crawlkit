---
schema: agents-md/v1
project: crawlkit
what: >-
  Domain-agnostic primitives for CDP-driven web scraping: CDP session, adapter
  framework, storage, weighted taxonomy classifier, structured logging,
  Prometheus metrics, rate limiting, robots.txt compliance. Extracted from
  ccarchive for reuse across projects.
goal: >-
  Break the "every project reimplements its own scraper" pattern. Provide
  production-grade primitives that any Python project can `pip install -e
  ./crawlkit` to get a full web ingestion + classification + observability
  stack without rebuilding from scratch.
status: active
stack: [python, playwright, pydantic, prometheus-client, beautifulsoup4, lxml]
entrypoints:
  - crawlkit.textutil
  - crawlkit.urlutil
  - crawlkit.datetimeutil
  - crawlkit.metrics
  - crawlkit.logsetup
  - crawlkit.robots
  - crawlkit.health
  - crawlkit.pacing
  - crawlkit.browser        # phase 2
  - crawlkit.adapters.base  # phase 2
  - crawlkit.storage        # phase 2
  - crawlkit.models         # phase 2
  - crawlkit.classifier     # phase 2
modules:
  - name: Text utilities
    path: crawlkit/textutil.py
    does: Text normalization, dedup, paragraph assembly
    status: shipped
  - name: URL utilities
    path: crawlkit/urlutil.py
    does: URL parsing, normalization, dedup-key extraction
    status: shipped
  - name: Date utilities
    path: crawlkit/datetimeutil.py
    does: Date parsing across formats, epoch conversion
    status: shipped
  - name: Prometheus metrics
    path: crawlkit/metrics.py
    does: Counters, histograms, gauges + exposition
    status: shipped
  - name: Structured logging
    path: crawlkit/logsetup.py
    does: JSON logging + StructuredLogger with bind/timer
    status: shipped
  - name: Robots.txt gate
    path: crawlkit/robots.py
    does: Compliance check before fetch
    status: shipped
  - name: Health probe
    path: crawlkit/health.py
    does: Pre-flight connectivity + DOM integrity check
    status: shipped
  - name: Rate limiter
    path: crawlkit/pacing.py
    does: Token-bucket pacer per host
    status: shipped
  - name: CDP browser session
    path: crawlkit/browser.py
    does: Chrome DevTools Protocol session + media aborter + age-gate dismisser
    status: planned
  - name: Adapter base classes
    path: crawlkit/adapters/base.py
    does: PatternCrawlAdapter + SourceAdapter base classes for multi-source ingestion
    status: planned
  - name: SQLite storage
    path: crawlkit/storage.py
    does: Idempotent upsert + normalized tag tables + JSONL/CSV export
    status: planned
  - name: Pydantic models
    path: crawlkit/models.py
    does: ParsedStory + StoryRecord data models
    status: planned
  - name: Weighted taxonomy classifier
    path: crawlkit/classifier.py
    does: Layer-3 multi-source scoring with confidence
    status: planned
updated: 2026-08-19 17:42 UTC
---

# AGENTS.md — crawlkit

**Last Updated:** 2026-08-19 17:42 UTC

---

## What this is

Production-grade Python primitives for CDP-driven web scraping. Phase 1 ships utilities + observability (8 modules, ~750 LOC). Phase 2 adds browser + adapter + storage + models + classifier (5 modules, ~1,300 LOC).

Every module here is **domain-agnostic**. The adult-content-specific bits (xnxx_stories, fictionmania, literotica, ao3, rss_feed, reddit adapters, taxonomy.json niches) stay in `ccarchive`. crawlkit contains the machinery; ccarchive uses it for one specific vertical.

## Quick Reference

| Task | Use |
|---|---|
| Connect to a running Chrome | `from crawlkit.browser import CDPSession` (Phase 2) |
| Check robots.txt | `from crawlkit.robots import RobotsGate` |
| Pre-flight a URL | `from crawlkit.health import check_site` |
| Rate-limit per host | `from crawlkit.pacing import Pacer` |
| Prometheus counters/histos | `from crawlkit.metrics import *` |
| Structured JSON logs | `from crawlkit.logsetup import StructuredLogger` |
| Normalize text | `from crawlkit.textutil import normalize, dedup_paragraphs` |
| Parse a date | `from crawlkit.datetimeutil import parse_date` |
| Extract dedup-key from URL | `from crawlkit.urlutil import dedup_key` |

## Invariants & Guardrails

1. **Zero domain knowledge in this repo.** If a module imports anything from `ccarchive.adapters` or references specific adult-content niches, it does not belong in crawlkit.
2. **Each module is self-contained.** No cross-imports between crawlkit modules unless the dependency is fundamental (e.g., metrics depends on logsetup for logger setup).
3. **Re-export compatibility:** `ccarchive` continues to import via `from ccarchive.MODULE import ...` — the ccarchive modules become thin re-export shims. Backwards compat preserved.
4. **Tests live in `crawlkit/tests/`**, mirror module names. Phase 1 ships tests for textutil/urlutil/datetimeutil/metrics/logsetup/robots/health/pacing.

## Origin & Precedent

- **Source:** `~/Projects/ccarchive/ccarchive/` (production since 2026-08, 8 adapters, 7 unit tests passing)
- **Precedent:** `~/Projects/caption-primitives/` — "Nothing here runs standalone — pieces are meant to be ported into other repos' caption stages." Same pattern.
- **Decomposition plan:** see `~/Projects/agent-skills/MONETIZATION-GAPS-ROADMAP.md` Session 1 Track A "crawlkit extraction"

## Next Steps

1. Phase 1: extract 8 modules + write tests + commit
2. Phase 2: extract browser + adapters + storage + models + classifier (refactor ccarchive to use them)
3. Phase 3: migrate one siloed scraper (aquascrape) as proof of cross-project value
