"""Fuzzy human date strings -> ISO-8601 UTC."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

_ORDINAL = re.compile(r"\b(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)
_NOISE = re.compile(
    r"\b(posted|published|added|submitted|updated|created|on|at|by|date|last modified)\b[:\s]*",
    re.IGNORECASE,
)
_OF = re.compile(r"\bof\b", re.IGNORECASE)
_RELATIVE = re.compile(
    r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", re.IGNORECASE
)

_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d %B %Y %H:%M",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d %Y",
    "%b %d %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%A %d %B %Y",
    "%a %d %B %Y",
    "%A, %d %B %Y",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_date(
    raw: str | None, *, now: datetime | None = None
) -> tuple[str | None, bool]:
    if not raw:
        return None, False
    now = now or datetime.now(timezone.utc)
    s = raw.strip()

    m = _RELATIVE.search(s)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        deltas = {
            "second": timedelta(seconds=n),
            "minute": timedelta(minutes=n),
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
            "month": timedelta(days=30 * n),
            "year": timedelta(days=365 * n),
        }
        return (now - deltas[unit]).replace(microsecond=0).isoformat(), True

    s = _NOISE.sub(" ", s)
    s = _ORDINAL.sub(r"\1", s)
    s = _OF.sub(" ", s)
    s = re.sub(r"[,\u00a0]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .;|-")

    if not s:
        return None, False

    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return _fmt(dt), True
    except ValueError:
        pass

    for fmt in _FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            return _fmt(dt, date_only="%H" not in fmt), True
        except ValueError:
            continue

    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(*map(int, m.groups())).isoformat(), True
        except ValueError:
            pass
    return None, False


def _fmt(dt: datetime, date_only: bool = False) -> str:
    if date_only or (
        dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.tzinfo is None
    ):
        return dt.date().isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def year_of(iso: str | None) -> int | None:
    if not iso or len(iso) < 4 or not iso[:4].isdigit():
        return None
    return int(iso[:4])
