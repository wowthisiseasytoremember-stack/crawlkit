# SPRINT-3-BROWSER-DETAIL — Move `ccarchive/browser.py` + `probe.py`, extract `age_gates.py`

**Status:** Granular plan, pending Sprint 2 verification.
**Pre-conditions:**
- Phase 1 + Sprint 1 done ✓
- Sprint 2 done (storage.py in crawlkit) — needed because ssc_crawl.py uses both browser + storage
- browser.py depends on: `Pacer` (Phase 1), `RobotsGate` (Phase 1), `host_of` (Phase 1) — all in crawlkit ✓
- browser.py does NOT depend on models (verified earlier)

---

## Goal

Move `ccarchive/browser.py` (244 LOC) and `ccarchive/probe.py` (69 LOC) to crawlkit. Extract the Reddit-specific age-gate logic into a new `crawlkit/age_gates.py` pluggable dispatcher. Preserve ccarchive production behavior with shims.

## Why this sprint needs an extra module

The age-gate dismissal logic in `browser.py` is currently inline + Reddit-specific (clicks the "I am 18+" button via CSS selector). For crawlkit to be a clean primitives library, this must move out. Design: `AgeGateDispatcher` in crawlkit, with a `RedditAgeGate` handler in ccarchive. ccarchive's `CDPSession` wrapper subclasses or composes the dispatcher with the Reddit handler pre-registered.

## Files to touch

| File | Action |
|---|---|
| `~/Projects/crawlkit/crawlkit/browser.py` | CREATE — copy from ccarchive, strip Reddit-specific age-gate inline |
| `~/Projects/crawlkit/crawlkit/probe.py` | CREATE — copy from ccarchive |
| `~/Projects/crawlkit/crawlkit/age_gates.py` | CREATE — new pluggable dispatcher |
| `~/Projects/crawlkit/tests/test_browser.py` | CREATE — CDP mocking tests |
| `~/Projects/crawlkit/tests/test_probe.py` | CREATE — offline HTML string tests |
| `~/Projects/crawlkit/tests/test_age_gates.py` | CREATE — dispatcher routing tests |
| `~/Projects/ccarchive/ccarchive/browser.py` | REPLACE — thin shim that wraps with Reddit age-gate |
| `~/Projects/ccarchive/ccarchive/probe.py` | REPLACE — thin shim |
| `~/Projects/ccarchive/ccarchive/age_gates.py` | CREATE — RedditAgeGate handler |

## Step-by-step

### Step 1: Read source (10 min)
```bash
ssh ichabod@ichabod-linux "cat /home/ichabod/Projects/ccarchive/ccarchive/browser.py"
ssh ichabod@ichabod-linux "cat /home/ichabod/Projects/ccarchive/ccarchive/probe.py"
```
Identify:
- CDPSession class + FetchResult dataclass
- Age-gate logic: which CSS selectors, what URL patterns trigger it
- Media aborter: which resource types (image, media, font)
- Pacer + RobotsGate integration points

### Step 2: Write crawlkit/age_gates.py (45 min)
```python
"""Pluggable age-gate dispatcher.

A site-specific age gate (Reddit "I am 18+", Twitter "View this content",
Discord "Are you 18+" etc.) is a small piece of behavior that varies per
site. This module provides:

  AgeGateDispatcher — registry + dispatcher
  AgeGateHandler — base class (subclass per site)
  NoOpAgeGate — default; does nothing

Concrete handlers (e.g. RedditAgeGate) live in the consuming project
(ccarchive/age_gates.py) since they encode site-specific DOM knowledge.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable
from urllib.parse import urlparse

log = logging.getLogger(__name__)


class AgeGateHandler(ABC):
    """Base class for site-specific age-gate handlers."""

    host_pattern: str = ""  # e.g. "reddit.com"

    @abstractmethod
    async def dismiss(self, page) -> bool:
        """Attempt to dismiss the age gate on the given page.

        Returns True if dismissed, False if no gate found / failed.
        Should be fail-open: a failure should not crash the crawl.
        """
        ...


class NoOpAgeGate(AgeGateHandler):
    host_pattern = "*"

    async def dismiss(self, page) -> bool:
        return False


class AgeGateDispatcher:
    """Routes URL → handler based on host_pattern matching."""

    def __init__(self) -> None:
        self._handlers: list[AgeGateHandler] = [NoOpAgeGate()]

    def register(self, handler: AgeGateHandler) -> None:
        """Register a new handler. Replaces any existing handler with the same host_pattern."""
        self._handlers = [h for h in self._handlers if h.host_pattern != handler.host_pattern]
        self._handlers.insert(0, handler)

    async def dismiss(self, page, url: str) -> bool:
        """Find handler for URL's host and attempt dismissal."""
        host = urlparse(url).netloc
        for handler in self._handlers:
            if handler.host_pattern == "*":
                continue
            if handler.host_pattern in host or host.endswith("." + handler.host_pattern):
                return await handler.dismiss(page)
        # Fallback to NoOp
        for handler in self._handlers:
            if handler.host_pattern == "*":
                return await handler.dismiss(page)
        return False
```

### Step 3: Write crawlkit/browser.py (30 min)
- Copy from ccarchive/browser.py
- Replace inline age-gate with call to `AgeGateDispatcher.dismiss(page, url)`
- Strip Reddit-specific CSS selectors
- Replace `from .pacing import Pacer` → `from crawlkit.pacing import Pacer`
- Replace `from .robots import RobotsGate` → `from crawlkit.robots import RobotsGate`
- Replace `from .urlutil import host_of` → `from crawlkit.urlutil import host_of`

### Step 4: Write crawlkit/probe.py (15 min)
- Copy from ccarchive/probe.py
- Update imports

### Step 5: Write ccarchive/age_gates.py (30 min)
```python
"""ccarchive age-gate handlers — Reddit-specific DOM knowledge lives here."""

from __future__ import annotations

import logging

from crawlkit.age_gates import AgeGateHandler

log = logging.getLogger(__name__)


class RedditAgeGate(AgeGateHandler):
    """Dismiss the r/<sub> "I am 18+" interstitial."""

    host_pattern = "reddit.com"

    async def dismiss(self, page) -> bool:
        try:
            # Reddit's age gate has a button with id "confirm-button" or similar
            # As of 2026-08, the selector is button[type="submit"] after the age-gate modal
            await page.wait_for_selector('button[type="submit"]', timeout=3000)
            await page.click('button[type="submit"]')
            log.info("Reddit age gate dismissed")
            return True
        except Exception as e:
            log.debug(f"Reddit age gate not found or dismiss failed: {e}")
            return False
```

### Step 6: Replace ccarchive/browser.py with shim + Reddit wrapper (20 min)
```python
"""Re-export + Reddit age-gate wrapper — browser moved to crawlkit (2026-08-19 Sprint 3)."""
from crawlkit.browser import CDPSession as _CDPSession, FetchResult, RobotsGate
from crawlkit.age_gates import AgeGateDispatcher
from crawlkit.pacing import Pacer
from .age_gates import RedditAgeGate


class CDPSession(_CDPSession):
    """ccarchive CDPSession — pre-registers Reddit age-gate handler."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._age_gate_dispatcher = AgeGateDispatcher()
        self._age_gate_dispatcher.register(RedditAgeGate())
```

This is a class subclass, not a simple `import *`. Required because the dispatcher needs the Reddit handler registered BEFORE first use.

### Step 7: Tests (90 min total)

#### test_browser.py (45 min)
- Mock CDP via `unittest.mock` patches on `playwright.async_api.async_playwright`
- Test: `CDPSession` context manager entry/exit calls `async_playwright().start()` and `.stop()`
- Test: media aborter registers route handler for `image`, `media`, `font`
- Test: `Pacer(3.0)` enforced between fetches

#### test_probe.py (20 min)
- Test: `probe_url(url, html)` extracts title via CSS selector (no live Chrome)
- Test: returns `None` for empty HTML
- Test: handles malformed HTML gracefully

#### test_age_gates.py (25 min)
- Test: `AgeGateDispatcher` with no handlers → falls back to NoOp, returns False
- Test: register `RedditAgeGate(host_pattern="reddit.com")` → routes `https://www.reddit.com/r/x` correctly
- Test: register two handlers with different host_patterns → routes correctly
- Test: `host.endswith("." + pattern)` works for subdomains

### Step 8: Verify + smoke (30 min)
```bash
ssh ichabod@ichabod-linux "cd /home/ichabod/Projects/crawlkit && python3 -m unittest discover tests"
ssh ichabod@ichabod-linux "cd /home/ichabod/Projects/ccarchive && python3 -m unittest discover tests"
```
Expected: crawlkit 18+ tests OK; ccarchive 4-6 tests OK.

Smoke test:
```bash
ssh ichabod@ichabod-linux "cd /home/ichabod/Projects/ccarchive && python3 scripts/ssc_crawl.py --sub boypussy --limit 3 --db /tmp/sprint3_smoke.sqlite3"
```
Should fetch 3 rows, exercising:
- CDPSession context manager
- Reddit age-gate dismissal (new shim path)
- Browser fetch
- Storage upsert (Sprint 2 path)

### Step 9: Commit + push (10 min)
```bash
ssh ichabod@ichabod-linux "cd /home/ichabod/Projects/crawlkit && git add crawlkit/browser.py crawlkit/probe.py crawlkit/age_gates.py tests/ && git commit -m 'sprint 3 extracted browser and probe with pluggable age gate dispatcher'"
ssh ichabod@ichabod-linux "cd /home/ichabod/Projects/ccarchive && git add ccarchive/browser.py ccarchive/probe.py ccarchive/age_gates.py && git commit -m 'sprint 3 browser shim with reddit age gate handler'"
```

## Edge cases

- **Reddit age-gate selector drift** — Reddit changes DOM. Handler is best-effort + fail-open (logged, returns False, crawl continues).
- **Multiple age-gate layers** — Reddit has interstitial + sometimes login walls. Handler only handles the interstitial.
- **CDP version pinning** — Playwright 1.40+ used. Document in pyproject.toml. Pin to 1.40-1.45 range.
- **Subdomain matching** — `host.endswith("." + pattern)` ensures `old.reddit.com` matches `reddit.com` pattern.
- **Probe without CDP** — pure HTML string parsing; no Chrome needed for the test.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Reddit age-gate selector breaks → ssc_crawl.py fails silently | Medium | High | Fail-open + log; smoke test catches obvious breaks |
| CDP version drift between Playwright releases | Low | Medium | Pin in pyproject.toml |
| Class subclass shim breaks ccarchive scripts that `isinstance` check CDPSession | Low | Medium | Document the inheritance; ccarchive scripts use `from ccarchive.browser import CDPSession` which is the subclass |
| Test mocks don't match real Playwright API | Medium | Medium | Use real Chrome for at least one integration test (ssc_crawl.py smoke) |
| AgeGateDispatcher fails silently on unknown host | Certain | Low | NoOp returns False; logs at DEBUG level |

## Time estimate

| Phase | Time |
|---|---|
| Read + plan | 10 min |
| age_gates.py dispatcher | 45 min |
| browser.py + probe.py move | 45 min |
| ccarchive shim + Reddit handler | 50 min |
| Tests (3 files) | 90 min |
| Verify + smoke | 30 min |
| Commit + push | 10 min |
| **Total** | **4.5-5 hrs** |

## Definition of done

- [ ] `crawlkit/browser.py`, `crawlkit/probe.py`, `crawlkit/age_gates.py` exist
- [ ] ccarchive shims preserve historical behavior (Reddit age-gate still fires)
- [ ] crawlkit 18+ tests pass (15 from Sprint 2 + 3 new files)
- [ ] ccarchive 4-6 tests pass
- [ ] `python3 scripts/ssc_crawl.py --sub boypussy --limit 3` smoke test works
- [ ] Committed + pushed to origin

## Out of scope (for Sprint 3)

- Multi-page CDP coordination (page pool, tab reuse) — Sprint 4 or later
- CDP screenshot/visual regression testing — Sprint 5+
- Browser fingerprint randomization — Sprint 5+ (Milestone 4 anti-detection)
