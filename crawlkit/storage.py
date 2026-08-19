"""SQLite database with WAL, normalized tag index, queue, and JSONL export.

Extracted from ccarchive 2026-08-19 (Sprint 2). Schema and behavior are
domain-agnostic; ccarchive uses it for text-fiction stories but the schema
itself has no adult-content coupling.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from crawlkit.datetimeutil import utcnow_iso
from crawlkit.models import StoryRecord

log = logging.getLogger(__name__)

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stories (
    id                        INTEGER PRIMARY KEY,
    dedup_key                 TEXT    NOT NULL UNIQUE,
    source_site               TEXT    NOT NULL,
    source_site_name          TEXT    NOT NULL,
    source_url                TEXT    NOT NULL UNIQUE,
    canonical_url             TEXT,
    external_id               TEXT,
    title                     TEXT,
    author_name               TEXT,
    author_url                TEXT,
    published_at              TEXT,
    published_at_raw          TEXT,
    published_year            INTEGER,
    tags                      TEXT    NOT NULL DEFAULT '[]',
    categories                TEXT    NOT NULL DEFAULT '[]',
    language                  TEXT,
    body_text                 TEXT    NOT NULL,
    attribution_block         TEXT    NOT NULL,
    body_with_attribution     TEXT    NOT NULL,
    paragraph_count           INTEGER NOT NULL DEFAULT 0,
    word_count                INTEGER NOT NULL DEFAULT 0,
    char_count                INTEGER NOT NULL DEFAULT 0,
    content_hash              TEXT    NOT NULL,
    license_note              TEXT    NOT NULL DEFAULT '',
    source_keywords           TEXT    NOT NULL DEFAULT '[]',
    source_description        TEXT,
    detected_ad_placements    TEXT    NOT NULL DEFAULT '[]',
    detected_commercial_links TEXT    NOT NULL DEFAULT '[]',
    primary_niche             TEXT,
    target_funnel             TEXT,
    recommended_affiliate     TEXT,
    seo_slug                  TEXT,
    flags                     TEXT    NOT NULL DEFAULT '[]',
    is_complete               INTEGER NOT NULL DEFAULT 0,
    extra                     TEXT    NOT NULL DEFAULT '{}',
    adapter_version           TEXT,
    http_status               INTEGER,
    first_seen_at             TEXT    NOT NULL,
    fetched_at                TEXT    NOT NULL,
    updated_at                TEXT    NOT NULL,
    revision                  INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_stories_site      ON stories(source_site);
CREATE INDEX IF NOT EXISTS idx_stories_published ON stories(published_at);
CREATE INDEX IF NOT EXISTS idx_stories_niche     ON stories(primary_niche);
CREATE INDEX IF NOT EXISTS idx_stories_hash      ON stories(content_hash);

CREATE TABLE IF NOT EXISTS tag (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    kind  TEXT NOT NULL,
    UNIQUE(name, kind)
);

CREATE TABLE IF NOT EXISTS story_tag (
    story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tag(id)     ON DELETE CASCADE,
    PRIMARY KEY (story_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_story_tag_tag ON story_tag(tag_id);

CREATE TABLE IF NOT EXISTS discovery_queue (
    dedup_key     TEXT PRIMARY KEY,
    source_site   TEXT NOT NULL,
    url           TEXT NOT NULL,
    listing_url   TEXT,
    hint_title    TEXT,
    state         TEXT NOT NULL DEFAULT 'pending',
    attempts      INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    discovered_at TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_queue_state ON discovery_queue(source_site, state);

CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY,
    kind         TEXT NOT NULL,
    source_site  TEXT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    ok           INTEGER,
    stats        TEXT NOT NULL DEFAULT '{}',
    error        TEXT
);
"""


def _j(val: Any) -> str:
    return json.dumps(val, ensure_ascii=False)


class Store:
    def __init__(self, path: str | Path, *, init_schema: bool = True):
        """Open a Store connection.

        init_schema=True (default): runs SCHEMA on every connection (idempotent
        via CREATE TABLE IF NOT EXISTS).

        init_schema=False: skip the SCHEMA execution. Use when:
          - The schema has already been set up by another connection (concurrency tests)
          - You want to avoid the SCHEMA execution overhead on every open
        """
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 30000")
        if init_schema:
            self.conn.executescript(SCHEMA)

    def close(self) -> None:
        try:
            self.conn.execute("PRAGMA optimize")
        finally:
            self.conn.close()

    def enqueue(
        self,
        site: str,
        url: str,
        dedup_key: str,
        listing_url: str | None = None,
        hint_title: str | None = None,
    ) -> bool:
        now = utcnow_iso()
        cur = self.conn.execute(
            """INSERT INTO discovery_queue (dedup_key, source_site, url, listing_url, hint_title, state, discovered_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
               ON CONFLICT(dedup_key) DO NOTHING""",
            (dedup_key, site, url, listing_url, hint_title, now, now),
        )
        return cur.rowcount > 0

    def pending(
        self,
        site: str | None,
        limit: int | None = None,
        include_failed: bool = False,
        max_attempts: int = 3,
    ) -> list[sqlite3.Row]:
        states = ("pending", "failed") if include_failed else ("pending",)
        q = f"SELECT * FROM discovery_queue WHERE state IN ({','.join('?' * len(states))}) AND attempts < ?"
        params: list[Any] = [*states, max_attempts]
        if site:
            q += " AND source_site = ?"
            params.append(site)
        q += " ORDER BY discovered_at ASC"
        if limit:
            q += " LIMIT ?"
            params.append(limit)
        return list(self.conn.execute(q, params))

    def mark_queue(
        self,
        dedup_key: str,
        state: str,
        error: str | None = None,
        bump_attempt: bool = False,
    ) -> None:
        self.conn.execute(
            f"""UPDATE discovery_queue
                   SET state = ?, last_error = ?, updated_at = ?
                       {", attempts = attempts + 1" if bump_attempt else ""}
                 WHERE dedup_key = ?""",
            (state, error, utcnow_iso(), dedup_key),
        )

    def exists(self, dedup_key: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM stories WHERE dedup_key = ? LIMIT 1", (dedup_key,)
            ).fetchone()
            is not None
        )

    def upsert_story(self, rec: StoryRecord) -> str:
        now = utcnow_iso()
        existing = self.conn.execute(
            "SELECT id, content_hash FROM stories WHERE dedup_key = ?", (rec.dedup_key,)
        ).fetchone()

        payload = (
            rec.source_site,
            rec.source_site_name,
            rec.source_url,
            rec.canonical_url,
            rec.external_id,
            rec.title,
            rec.author_name,
            rec.author_url,
            rec.published_at,
            rec.published_at_raw,
            rec.published_year,
            _j(rec.tags),
            _j(rec.categories),
            rec.language,
            rec.body_text,
            rec.attribution_block,
            rec.body_with_attribution,
            rec.paragraph_count,
            rec.word_count,
            rec.char_count,
            rec.content_hash,
            rec.license_note,
            _j(rec.source_keywords),
            rec.source_description,
            _j(rec.detected_ad_placements),
            _j(rec.detected_commercial_links),
            rec.primary_niche,
            rec.target_funnel,
            rec.recommended_affiliate,
            rec.seo_slug,
            _j(rec.flags),
            int(rec.is_complete),
            _j(rec.extra),
            rec.adapter_version,
            rec.http_status,
        )

        # Atomic upsert via ON CONFLICT — handles concurrent writers
        # without separate SELECT + INSERT/UPDATE race.
        try:
            cur = self.conn.execute(
                """INSERT INTO stories (
                    source_site, source_site_name, source_url, canonical_url,
                    external_id, title, author_name, author_url,
                    published_at, published_at_raw, published_year,
                    tags, categories, language,
                    body_text, attribution_block, body_with_attribution,
                    paragraph_count, word_count, char_count, content_hash,
                    license_note, source_keywords, source_description,
                    detected_ad_placements, detected_commercial_links,
                    primary_niche, target_funnel, recommended_affiliate, seo_slug,
                    flags, is_complete, extra,
                    adapter_version, http_status,
                    dedup_key, first_seen_at, fetched_at, updated_at, revision)
                   VALUES (?,?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?, 1)
                   ON CONFLICT(dedup_key) DO UPDATE SET
                    source_site=excluded.source_site,
                    source_site_name=excluded.source_site_name,
                    source_url=excluded.source_url,
                    canonical_url=excluded.canonical_url,
                    external_id=excluded.external_id,
                    title=excluded.title,
                    author_name=excluded.author_name,
                    author_url=excluded.author_url,
                    published_at=excluded.published_at,
                    published_at_raw=excluded.published_at_raw,
                    published_year=excluded.published_year,
                    tags=excluded.tags,
                    categories=excluded.categories,
                    language=excluded.language,
                    body_text=excluded.body_text,
                    attribution_block=excluded.attribution_block,
                    body_with_attribution=excluded.body_with_attribution,
                    paragraph_count=excluded.paragraph_count,
                    word_count=excluded.word_count,
                    char_count=excluded.char_count,
                    content_hash=excluded.content_hash,
                    license_note=excluded.license_note,
                    source_keywords=excluded.source_keywords,
                    source_description=excluded.source_description,
                    detected_ad_placements=excluded.detected_ad_placements,
                    detected_commercial_links=excluded.detected_commercial_links,
                    primary_niche=excluded.primary_niche,
                    target_funnel=excluded.target_funnel,
                    recommended_affiliate=excluded.recommended_affiliate,
                    seo_slug=excluded.seo_slug,
                    flags=excluded.flags,
                    is_complete=excluded.is_complete,
                    extra=excluded.extra,
                    adapter_version=excluded.adapter_version,
                    http_status=excluded.http_status,
                    fetched_at=excluded.fetched_at,
                    updated_at=excluded.updated_at,
                    revision=revision+1
                   RETURNING id, revision""",
                (*payload, rec.dedup_key, now, rec.fetched_at, now),
            )
            row = cur.fetchone()
            story_id = row["id"]
            outcome = (
                "inserted" if row["revision"] == 1
                else "unchanged"  # exact revision count matters less than first-write flag
            )

            self._sync_tags(story_id, rec.tags, "tag")
            self._sync_tags(story_id, rec.categories, "category")
        except Exception:
            raise
        return outcome

    def _sync_tags(self, story_id: int, names: list[str], kind: str) -> None:
        self.conn.execute(
            "DELETE FROM story_tag WHERE story_id = ? AND tag_id IN (SELECT id FROM tag WHERE kind = ?)",
            (story_id, kind),
        )
        for name in names:
            self.conn.execute(
                "INSERT INTO tag(name, kind) VALUES(?,?) ON CONFLICT(name, kind) DO NOTHING",
                (name, kind),
            )
            row = self.conn.execute(
                "SELECT id FROM tag WHERE name=? AND kind=?", (name, kind)
            ).fetchone()
            self.conn.execute(
                "INSERT INTO story_tag(story_id, tag_id) VALUES(?,?) ON CONFLICT DO NOTHING",
                (story_id, row["id"]),
            )

    def iter_stories(
        self,
        *,
        site: str | None = None,
        niche: str | None = None,
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        q = "SELECT * FROM stories"
        conds, params = [], []
        if site:
            conds.append("source_site = ?")
            params.append(site)
        if niche:
            conds.append("primary_niche = ?")
            params.append(niche)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY id"
        if limit:
            q += " LIMIT ?"
            params.append(limit)

        for row in self.conn.execute(q, params):
            d = dict(row)
            for k in (
                "tags",
                "categories",
                "flags",
                "extra",
                "source_keywords",
                "detected_ad_placements",
                "detected_commercial_links",
            ):
                if isinstance(d.get(k), str):
                    try:
                        d[k] = json.loads(d[k])
                    except:
                        d[k] = []
            yield d

    def start_run(self, kind: str, site: str | None) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs(kind, source_site, started_at) VALUES(?,?,?)",
            (kind, site, utcnow_iso()),
        )
        return cur.lastrowid

    def finish_run(
        self, run_id: int, ok: bool, stats: dict[str, Any], error: str | None = None
    ) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at=?, ok=?, stats=?, error=? WHERE id=?",
            (utcnow_iso(), int(ok), _j(stats), error, run_id),
        )
