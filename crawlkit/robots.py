"""Minimal robots.txt gate."""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

log = logging.getLogger(__name__)


class RobotsGate:
    def __init__(
        self, user_agent: str = "*", enabled: bool = True, timeout: float = 10.0
    ):
        self.user_agent = user_agent
        self.enabled = enabled
        self.timeout = timeout
        self._cache: dict[str, RobotFileParser | None] = {}

    def _parser(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._cache:
            return self._cache[origin]
        rp = RobotFileParser()
        robots_url = origin + "/robots.txt"
        try:
            req = urllib.request.Request(
                robots_url, headers={"User-Agent": "ccarchive/0.2"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                rp.parse(resp.read().decode("utf-8", "replace").splitlines())
            log.info("robots: loaded %s", robots_url)
        except Exception as exc:
            log.warning(
                "robots: could not fetch %s (%s); treating as permissive",
                robots_url,
                exc,
            )
            rp = None
        self._cache[origin] = rp
        return rp

    def allowed(self, url: str) -> bool:
        if not self.enabled:
            return True
        rp = self._parser(url)
        if rp is None:
            return True
        return rp.can_fetch(self.user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        rp = self._parser(url)
        if rp is None:
            return None
        try:
            d = rp.crawl_delay(self.user_agent)
            return float(d) if d is not None else None
        except Exception:
            return None
