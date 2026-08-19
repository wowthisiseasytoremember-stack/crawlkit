# crawlkit

Domain-agnostic primitives for CDP-driven web scraping. Extracted from `ccarchive` (text-fiction ingestion) for reuse across projects that need browser automation, multi-source data ingestion, taxonomy classification, or pipeline observability.

## What this is

Production-grade Python primitives — extracted to break the "every project reimplements its own scraper" pattern. Following the `caption-primitives` precedent: nothing here runs standalone; pieces are imported by other repos.

## Modules

| Module | LOC | What it does |
|---|---|---|
| `textutil.py` | ~190 | Text normalization, dedup, paragraph assembly |
| `urlutil.py` | ~50 | URL parsing, normalization, dedup-key extraction |
| `datetimeutil.py` | ~110 | Date parsing across formats, epoch conversion |
| `metrics.py` | ~200 | Prometheus metrics (counters, histograms, gauges) + exposition |
| `logsetup.py` | ~70 | JSON structured logging + `StructuredLogger.bind/timer` |
| `robots.py` | ~65 | robots.txt compliance gate |
| `health.py` | ~75 | Pre-flight connectivity + DOM integrity check |
| `pacing.py` | ~50 | Token-bucket rate limiter per host |
| `probe.py` | ~70 | Selector probe against live URL |
| `browser.py` | ~245 | CDP session (Chrome DevTools Protocol) + media aborter + age-gate dismisser |
| `adapters/base.py` | ~125 | `PatternCrawlAdapter` + `SourceAdapter` base classes |
| `storage.py` | ~365 | SQLite with idempotent upsert, normalized tag tables, JSONL/CSV export |
| `models.py` | ~305 | Pydantic models for parsed stories + records |
| `classifier.py` | ~270 | Layer-3 weighted taxonomy scoring with confidence |

**Phase 1 (initial release):** utilities + observability (textutil, urlutil, datetimeutil, metrics, logsetup, robots, health, pacing) — zero domain knowledge.

**Phase 2 (next):** browser + adapter + storage + models + classifier.

## Install

```bash
pip install -e ~/Projects/crawlkit
```

Or copy the modules you need into your project — they're self-contained.

## Projects using crawlkit

- `ccarchive` — text-fiction ingestion (canonical source)
- (more to come — Phase 3 cross-project migration)

## Origin

Extracted 2026-08-19 from `~/Projects/ccarchive/ccarchive/` per the decomposition plan in
`~/Projects/agent-skills/MONETIZATION-GAPS-ROADMAP.md` Session 1. Precedent: `~/Projects/caption-primitives/`.
