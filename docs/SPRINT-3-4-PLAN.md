# Sprint 3–4 Plan — Complete the crawlkit decomposition (verified 2026-08-20)

**Supersedes parts of:** `docs/PHASE-2-EXTRACTION-PLAN.md` and `docs/SPRINT-3-BROWSER-DETAIL.md` where noted.
**Status:** **Sprint 3 DONE (2026-08-20).** Sprint 1 (models+classifier) and Sprint 2 (storage) DONE. Remaining: Sprint 4 (adapters/base + probe) and Sprint 4.5 (glue).

---

## Current state (verified 2026-08-20)

| Module | LOC | In crawlkit? | Notes |
|---|---|---|---|
| textutil, urlutil, datetimeutil, metrics, logsetup, robots, health, pacing | — | ✅ Phase 1 | |
| models, classifier | 306/272 | ✅ Sprint 1 | ccarchive has shims; `classify_story()` taxonomy_path arg added |
| storage | 365 | ✅ Sprint 2 | ccarchive shim; concurrency-tested |
| **browser** | 244 | ✅ Sprint 3 | ccarchive shim; 11 mocked tests; `ccarch health`/`run` verified via shim |
| **probe** | 69 | ❌ still in ccarchive | deps: adapters.base, browser, models, textutil |
| **adapters/base** | 123 | ❌ still in ccarchive | deps: browser ✅, models ✅, textutil ✅, urlutil ✅ |
| pipeline | 90 | ❌ stays in ccarchive | domain glue; depends on adapters.base, browser, models, storage |
| cli | ~190 | ❌ stays in ccarchive | domain glue |

## Key finding vs. original plan

The original Sprint-3 detail assumed the age-gate dismissal in `browser.py` was
**Reddit-specific** and proposed a pluggable `AgeGateDispatcher` + `RedditAgeGate`
handler. **Verified false:** `browser.py` age-gate logic is fully generic — it
scans `CONSENT_SELECTORS` (CSS) then `CONSENT_TEXTS` (button labels) and clicks the
first visible match (`dismiss_interstitials()`, lines 155–174). No site-specific
DOM knowledge exists. Therefore:

- **DROP the `age_gates.py` dispatcher entirely** — it's 100+ lines of abstraction for a
  generic text/selector clicker that already lives in browser.py and moves cleanly.
- `dismiss_interstitials`, `CONSENT_SELECTORS`, `CONSENT_TEXTS` move **as-is** to crawlkit.
- Any future site-specific gate is a subclass override, not a dispatcher.

This cuts Sprint 3's scope and risk meaningfully (~45 min + a test file).

---

## Sprint 3 — browser.py (4-5 hrs → now ~3-4 hrs)

### Files
| File | Action |
|---|---|
| `~/Projects/crawlkit/crawlkit/browser.py` | CREATE — copy from ccarchive, rewrite 3 imports to `from crawlkit.X` |
| `~/Projects/crawlkit/tests/test_browser.py` | CREATE — mocked-Playwright tests (see below) |
| `~/Projects/ccarchive/ccarchive/browser.py` | REPLACE — one-line shim: `from crawlkit.browser import *` |

### Import rewrites (only changes)
- `from .pacing import Pacer` → `from crawlkit.pacing import Pacer`
- `from .robots import RobotsGate` → `from crawlkit.robots import RobotsGate`
- `from .urlutil import host_of` → `from crawlkit.urlutil import host_of`
- Loggers rename: `log = logging.getLogger("crawlkit.browser")`

Everything else (`CDPSession`, `FetchResult`, `FetchError`, `RobotsDisallowed`,
`BLOCKED_RESOURCE_TYPES`, `dismiss_interstitials`) copies verbatim.

### Tests (mock Playwright — no live Chrome)
1. `CDPSession.__aenter__` connects via `async_playwright().chromium.connect_over_cdp(endpoint)`.
2. Media aborter registers `page.route("**/*", _route_filter)` and aborts image/media/font.
3. `fetch()` raises `RobotsDisallowed` when robots.txt denies (patch `RobotsGate.allowed` → False).
4. HTTP 429 → `FetchError(status=429, retryable=True)` after `pacer.penalize`.
5. `dismiss_interstitials` clicks a matching `CONSENT_SELECTOR` and returns; no-op when none visible.
6. Retry/backoff: 2 consecutive failures → `FetchError`, `max_retries` honored.

### Smoke
```bash
cd ~/Projects/ccarchive && python3 -m ccarchive.cli health        # all 5 PASS
cd ~/Projects/ccarchive && python3 -m ccarchive.cli run --site literotica --limit 1 --max-pages 1
```

### Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Playwright API version drift | Low | Med | Pin `playwright>=1.40,<1.50` in crawlkit pyproject |
| Shim hides real import errors | Low | Med | Smoke test above exercises the shim path end-to-end |
| `from crawlkit.browser import *` misses names | Low | Low | `__all__` or explicit re-export in shim |

---

## Sprint 4 — adapters/base.py + probe.py (4-6 hrs)

### Dependency ordering fix
Original plan put probe in Sprint 3 and adapters/base in Sprint 4, but **probe.py imports
`from .adapters.base import SourceAdapter`** (probe.py:9). So probe moves **with** Sprint 4,
after base lands in crawlkit. Ordering: Sprint 3 (browser, DONE) → Sprint 4 (base) → Sprint 4.5 (probe, pipeline, cli glue).

### Files
| File | Action |
|---|---|
| `~/Projects/crawlkit/crawlkit/adapters/__init__.py` | CREATE — empty package init |
| `~/Projects/crawlkit/crawlkit/adapters/base.py` | CREATE — copy from ccarchive, rewrite imports |
| `~/Projects/crawlkit/crawlkit/probe.py` | CREATE — copy from ccarchive, rewrite imports |
| `~/Projects/ccarchive/ccarchive/adapters/base.py` | REPLACE — shim `from crawlkit.adapters.base import *` |
| `~/Projects/ccarchive/ccarchive/probe.py` | REPLACE — shim `from crawlkit.probe import *` |
| `~/Projects/crawlkit/tests/test_adapter_base.py` | CREATE — abstract contract + BFS discovery tests |
| `~/Projects/crawlkit/tests/test_probe.py` | CREATE — offline HTML-string probe test |

### Import rewrites in base.py
- `from ..browser import FetchResult` → `from crawlkit.browser import FetchResult`
- `from ..models import Discovered, ParsedStory` → `from crawlkit.models import ...`
- `from ..textutil import clean_inline, soup_of` → `from crawlkit.textutil import ...`
- `from ..urlutil import normalize_url, registrable_match` → `from crawlkit.urlutil import ...`
- `log = logging.getLogger("crawlkit.adapters.base")`

### probe.py rewrites
- `from .adapters.base import SourceAdapter` → `from crawlkit.adapters.base import SourceAdapter`
- `from .browser import CDPSession` → `from crawlkit.browser import CDPSession`
- `from .models import build_record` → `from crawlkit.models import build_record`
- `from .textutil import soup_of` → `from crawlkit.textutil import soup_of`

### Tests
1. `SourceAdapter` cannot be instantiated (abstract).
2. `PatternCrawlAdapter.discover` BFS: given a mock `fetch` returning crafted HTML, yields
   `Discovered` for story URLs, queues listing URLs to depth limit, dedups by `dedup_key`,
   never yields off-host links.
3. `is_story_url` / `is_listing_url` regex routing.
4. `probe_url` on an HTML string: extracts fields + attribution block; tolerant of missing
   author/date.

### Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 6 site adapters import `from ..browser` → now `from crawlkit.browser` | Med | High | They keep working via ccarchive shims, but migrate each to crawlkit imports in 4.5; smoke `ccarch probe --site <each>` |
| `adapters/__init__.py` registry imports `.base` → still resolves via shim | Low | Med | Registry untouched this sprint |
| Double shim hop (ccarchive.base → crawlkit.base) perf/indirection | Low | Low | Negligible at import time |

---

## Sprint 4.5 — glue refactor + verification (2-3 hrs)

1. Update ccarchive's 6 site adapters to import directly from crawlkit (drop `..` imports):
   `ao3.py, fictionmania.py, literotica.py, reddit.py, rss_feed.py, xnxx_stories.py`.
2. `ccarchive/pipeline.py` → `from crawlkit.adapters.base import SourceAdapter` etc.
3. `ccarchive/cli.py` → direct crawlkit imports (keep behavior identical).
4. ccarchive `browser.py`, `probe.py`, `adapters/base.py`, `models.py`, `classifier.py`,
   `storage.py` all become thin one-line shims.
5. Delete ccarchive copies of `textutil/urlutil/datetimeutil/metrics/logsetup/robots/pacing`
   only after grep confirms zero ccarchive importers (scripts + cli may still use shims).

### Definition of done (Sprint 4.5)
- [ ] `ccarch health` all 5 PASS
- [ ] `ccarch run --site literotica --limit 1 --max-pages 1` stores ≥1 row
- [ ] `ccarch probe --site <each of 5>` returns extracted fields
- [ ] crawlkit tests green (13 + new) and ccarchive tests green (6)
- [ ] `pip install -e ./crawlkit` in a fresh venv with NO ccarchive → imports crawlkit.browser/probe/adapters.base cleanly
- [ ] CHANGELOG entries in both repos; crawlkit pyproject bumped 0.1.0 → 0.2.0

---

## Timeline

| Sprint | Modules | Hours | Status |
|---|---|---|---|
| 3 | browser.py (no age_gates dispatcher — finding above) | 3-4 | ✅ DONE 2026-08-20 (crawlkit `3bbb8c8`, ccarchive `b7a20e8`) |
| 4 | adapters/base.py + probe.py | 4-6 | ⏳ next |
| 4.5 | glue refactor + clean-install verification | 2-3 | pending |
| **Total** | **6 files moved + shims + tests** | **9-13** | |

## Out of scope (unchanged from Phase 2 plan)
- Twitter/X + Bluesky adapters, audio adapters, semantic dedup, worker pool, per-site rate limiting, browser fingerprinting.
