# crawlkit Phase 2 — Extraction Plan

**Status:** Planning (2026-08-19) — execution after Phase 1 verification.
**Goal:** Move 5 more modules from `ccarchive` to `crawlkit` so any project can `pip install -e ./crawlkit` for a full CDP-driven ingest + classification + observability stack.
**Estimated effort:** 15-20 hours focused work, 4 sprints.

---

## Why Phase 2

Phase 1 (8 utility/observability modules) shipped 2026-08-19 — all 7 ccarchive tests pass, backwards compat verified. But the **interesting** primitives (CDP browser session, adapter framework, SQLite storage, weighted classifier, Pydantic models) are still in ccarchive. Phase 2 moves them so projects beyond ccarchive can build on them.

Concrete Phase 2 beneficiaries:
- **aquascrape, fish-atlas-scraper** — full CDP + adapter stack, currently siloed
- **job-search** — needs browser.py for career-site scraping
- **shame-seo** — needs classifier.py + storage.py for content categorization
- **reputation-mvp** — already has a similar `BaseSource` plan; Phase 2 unblocks their extraction
- **ebay-store** (specifically `photo-pipeline-vision`) — needs storage + browser for product research

---

## Dependency Map (from ccarchive internal imports)

```
classifier.py   INDEPENDENT (no ccarchive deps)
browser.py      → pacing ✓, robots ✓, urlutil ✓
models.py       → datetimeutil ✓, textutil ✓
storage.py      → datetimeutil ✓, models
adapters/base.py → browser, models, textutil ✓, urlutil ✓
pipeline.py     → adapters.base, browser, models, storage
probe.py        → adapters.base, browser, models, textutil ✓
cli.py          → adapters, browser, health, logsetup, metrics, models, pacing, probe, robots, storage
```

✓ = already in crawlkit Phase 1.

---

## Extraction Order (4 sprints)

### Sprint 1 — Models + Classifier (parallel, no inter-deps) — 3-4 hrs

**Extract:**
- `ccarchive/models.py` (306 LOC) → `crawlkit/models.py`
- `ccarchive/classifier.py` (272 LOC) → `crawlkit/classifier.py`

**Why first:** Models is the data contract every other module depends on. Classifier is fully independent.

**Refactor:**
- `models.py` imports stay local (`from crawlkit.datetimeutil`, `from crawlkit.textutil`)
- `classifier.py` takes `taxonomy_path` as constructor arg instead of hard-coded path
- `taxonomy.json` stays in ccarchive (domain-specific adult niches); ccarchive subclasses with its default taxonomy
- Add `ccarchive/models.py` + `ccarchive/classifier.py` shims re-exporting from crawlkit
- Update `ccarchive/classifier.py` shim to default-inject `taxonomy.json` from ccarchive's location (preserves `from ccarchive.classifier import classify_story` working without specifying path)

**Tests:**
- Move `tests/test_classifier.py` to `crawlkit/tests/test_classifier.py`
- Add `crawlkit/tests/test_models.py` (new — none in ccarchive)
- Add `crawlkit/tests/test_classifier_taxonomy_arg.py` (new — verify custom taxonomy paths)
- Run ccarchive tests: still 7 passing

**Risks:**
- `Flag` constants class in models — pure enum-like, easy to move
- `build_record` function depends on `body_with_attribution` string template — check no other module overrides it

---

### Sprint 2 — Storage (depends on Models) — 4-5 hrs

**Extract:**
- `ccarchive/storage.py` (365 LOC) → `crawlkit/storage.py`

**Refactor:**
- `Store` class moves to crawlkit
- `Store.__init__` takes optional `taxonomy_loader` for classifier integration (or stays decoupled — keep decoupled for now)
- Schema initialization (DDL strings) move with the class
- `ccarchive/storage.py` becomes a thin shim
- All `from ccarchive.storage import Store` call sites in `scripts/*.py` and `cli.py` continue to work via shim

**Tests:**
- Move `tests/test_storage.py` to `crawlkit/tests/test_storage.py`
- Verify SQLite WAL mode + idempotent upsert + JSONL/CSV export still work
- Add a cross-process concurrency test (two processes writing same DB)

**Risks:**
- SQLite path conventions — `data/*.sqlite3` paths are ccarchive-specific. `Store` should accept any path. Verify.
- Tag normalization table — currently `INSERT OR IGNORE INTO tag (name, kind)` — pure SQL, moves cleanly

---

### Sprint 3 — Browser + Probe (depends on Phase 1 only) — 4-5 hrs

**Extract:**
- `ccarchive/browser.py` (244 LOC) → `crawlkit/browser.py`
- `ccarchive/probe.py` (69 LOC) → `crawlkit/probe.py`

**Refactor:**
- `CDPSession` context manager moves to crawlkit
- `RobotsGate`, `Pacer`, `host_of` already in crawlkit (Phase 1 ✓)
- `probe.py` imports `from .browser import CDPSession` → `from crawlkit.browser import CDPSession`
- `ccarchive/browser.py` and `ccarchive/probe.py` become shims
- `ccarchive/scripts/*.py` keep working — most already use `from ccarchive.browser import CDPSession`

**Tests:**
- Add `crawlkit/tests/test_browser.py` — needs CDP, but can mock with pytest-playwright fixtures
- Add `crawlkit/tests/test_probe.py` — selector probe against HTML string (no live Chrome needed)

**Risks:**
- **CDP version drift:** Playwright's CDP wrapper version changes; document supported Playwright version range
- **Age-gate dismissal** in browser.py is Reddit-specific (dismisses "I am 18+" interstitial) — that's a site convention, NOT domain-agnostic. Either: (a) move it to a separate `age_gates.py` helper, or (b) leave it as a "Reddit-specific override" in ccarchive that subclasses browser.py. **Recommend (a) — extract to `crawlkit/age_gates.py` as a pluggable dispatcher.**
- **Media aborter** — generic, moves cleanly

---

### Sprint 4 — Adapter Base (depends on Browser + Models) — 4-6 hrs

**Extract:**
- `ccarchive/adapters/base.py` (123 LOC) → `crawlkit/adapters/base.py`

**Refactor:**
- `PatternCrawlAdapter` (HTML scraping) + `SourceAdapter` (non-HTML, e.g., RSS) move to crawlkit
- Import paths change: `from ..browser import FetchResult` → `from crawlkit.browser import FetchResult`, etc.
- All 6 site adapters (xnxx_stories, literotica, ao3, rss_feed, fictionmania, reddit) STAY in ccarchive — they're domain-specific
- Each site adapter imports from crawlkit, not from `..browser` etc.
- `ccarchive/adapters/base.py` becomes a shim re-exporting from crawlkit (preserves `from ccarchive.adapters.base import SourceAdapter` working)

**Tests:**
- Move `tests/test_adapter_helpers.py` to `crawlkit/tests/test_adapter_helpers.py`
- Add `crawlkit/tests/test_adapter_base.py` — verify abstract methods enforce subclass contract
- Add an integration test: subclass `PatternCrawlAdapter`, mock HTML, verify discover → fetch → parse flow

**Risks:**
- `ccarchive/adapters/` is a package, not a file. The `__init__.py` registry uses `from . import xnxx_stories` etc. — those local imports stay. Only the `base.py` moves.
- `from ..browser` style imports in `base.py` need careful rewrite to absolute `from crawlkit.browser`

---

## Cross-cutting refactor (Sprint 4.5)

After Sprint 4 lands, refactor ccarchive glue:

- `ccarchive/pipeline.py` — change all `from .adapters.base import SourceAdapter` → `from crawlkit.adapters.base import SourceAdapter` (or keep shim working — cleaner to use crawlkit directly)
- `ccarchive/probe.py` — same
- `ccarchive/cli.py` — change all `from .X import Y` to `from crawlkit.X import Y` (or keep via shim)
- `ccarchive/scripts/*.py` — same
- Verify all 7 ccarchive tests still pass after direct imports (not via shims)
- Verify `python3 -m ccarchive.cli health --site xnxx_stories` still works (full smoke test)

---

## Phase 2 Deliverables Checklist

- [ ] 5 modules moved (models, classifier, storage, browser, probe, adapters/base) — actually 6 modules
- [ ] All shims in place, backwards compat verified
- [ ] Test suite green: ccarchive 7 tests + crawlkit ≥10 tests
- [ ] `pip install -e ./crawlkit` works for clean install (no ccarchive present)
- [ ] CI/CD updated: crawlkit has its own GitHub Actions
- [ ] pyproject.toml bumped to 0.2.0
- [ ] AGENTS.md + README.md updated with new modules
- [ ] ccarchive CHANGELOG entry documenting the extraction
- [ ] CHANGELOG.md in crawlkit initialized
- [ ] Tag + push: `crawlkit v0.2.0`

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Subtle behavior change after move (e.g., relative import resolution) | Medium | High | Keep shims; run all 7 ccarchive tests after each sprint; smoke-test `ccarch health` |
| `age_gates.py` extraction breaks Reddit adapter | Medium | Medium | Sprint 3 — add `age_gates.py` pluggable dispatcher; Reddit adapter uses default Reddit-specific handler |
| Classifier `taxonomy_path` API change breaks ccarchive callers | Low | High | Sprint 1 shim defaults to ccarchive's `taxonomy.json` when no path passed |
| Test coverage gap after move (e.g., `test_models.py` doesn't exist) | High | Medium | Each sprint creates new tests in crawlkit/tests/ for the extracted module |
| Concurrent SQLite writes break under storage.py move | Low | Medium | Sprint 2 adds a multi-process concurrency test |
| Adapter base extraction breaks 6 site adapters | Medium | High | Sprint 4 keeps shim working; smoke-test each adapter via `ccarch probe --site <name>` |

---

## Timeline

| Sprint | Modules | Hours | Day estimate |
|---|---|---|---|
| 1 | models + classifier | 3-4 | Day 1 |
| 2 | storage | 4-5 | Day 2 |
| 3 | browser + probe + age_gates | 4-5 | Day 3 |
| 4 | adapters/base + glue refactor | 4-6 | Day 4 |
| **Total** | **6 modules + refactor** | **15-20** | **~4 working days** |

---

## Out of Scope for Phase 2

- Twitter/X + Bluesky adapters (need new work, not just extraction)
- Audio format adapters (Reddit GWA — needs different adapter pattern)
- Semantic dedup (Milestone 5 from ccarchive ROADMAP)
- Worker pool / multi-process (Milestone 5)
- Token-bucket per-site rate limiting (Milestone 4 from ccarchive ROADMAP — partially in Phase 1)

---

## Cross-Project Migration Targets (Phase 3, post-extraction)

Once crawlkit is at 0.2.0:
1. **aquascrape** — migrate its siloed scraper to `crawlkit.adapters.base.PatternCrawlAdapter`
2. **fish-atlas-scraper** — migrate to `crawlkit` (already noted in reputation-mvp extraction plan)
3. **job-search** — adopt `crawlkit.browser` for career-site scraping
4. **shame-seo** — adopt `crawlkit.classifier` for content categorization

Each migration is its own sprint, ~5-10 hrs each.
