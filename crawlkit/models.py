"""Core data structures, quality flags, and attribution builders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crawlkit.datetimeutil import utcnow_iso, year_of
from crawlkit.textutil import content_hash, word_count

ATTRIBUTION_SEPARATOR = "\n\n---\n### Source & Archival Attribution\n"


class Flag:
    MISSING_TITLE = "missing_title"
    MISSING_AUTHOR = "missing_author"
    MISSING_DATE = "missing_date"
    UNPARSEABLE_DATE = "unparseable_date"
    MISSING_TAGS = "missing_tags"
    MISSING_CANONICAL = "missing_canonical"
    EMPTY_BODY = "empty_body"
    SHORT_BODY = "short_body"
    BODY_FALLBACK_HEURISTIC = "body_fallback_heuristic"
    TRUNCATED_MULTIPAGE = "truncated_multipage"
    UNCLASSIFIED_TAXONOMY = "unclassified_taxonomy"


@dataclass(slots=True)
class Discovered:
    url: str
    dedup_key: str
    listing_url: str | None = None
    hint_title: str | None = None


@dataclass(slots=True)
class ParsedStory:
    source_url: str
    dedup_key: str
    canonical_url: str | None = None
    external_id: str | None = None
    title: str | None = None
    author_name: str | None = None
    author_url: str | None = None
    published_at: str | None = None
    published_at_raw: str | None = None
    tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    body_paragraphs: list[str] = field(default_factory=list)
    language: str | None = "en"

    # Layer 2: On-Page Ad & SEO Metadata
    source_keywords: list[str] = field(default_factory=list)
    source_description: str | None = None
    detected_ad_placements: list[str] = field(default_factory=list)
    detected_commercial_links: list[str] = field(default_factory=list)

    # Layer 3: Taxonomy & Funnel
    primary_niche: str | None = None
    target_funnel: str | None = None
    recommended_affiliate: str | None = None
    seo_slug: str | None = None
    classification_confidence: float | None = None

    extra: dict[str, Any] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    http_status: int | None = None

    def add_flag(self, flag: str) -> None:
        if flag not in self.flags:
            self.flags.append(flag)


@dataclass(slots=True)
class StoryRecord:
    dedup_key: str
    source_site: str
    source_site_name: str
    source_url: str
    canonical_url: str | None
    external_id: str | None
    title: str | None
    author_name: str | None
    author_url: str | None
    published_at: str | None
    published_at_raw: str | None
    published_year: int | None
    tags: list[str]
    categories: list[str]
    language: str | None
    body_text: str
    attribution_block: str
    body_with_attribution: str
    paragraph_count: int
    word_count: int
    char_count: int
    content_hash: str
    license_note: str

    source_keywords: list[str]
    source_description: str | None
    detected_ad_placements: list[str]
    detected_commercial_links: list[str]

    primary_niche: str | None
    target_funnel: str | None
    recommended_affiliate: str | None
    seo_slug: str | None
    classification_confidence: float | None

    flags: list[str]
    is_complete: bool
    extra: dict[str, Any]
    adapter_version: str
    http_status: int | None
    fetched_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dedup_key": self.dedup_key,
            "source_site": self.source_site,
            "source_site_name": self.source_site_name,
            "source_url": self.source_url,
            "canonical_url": self.canonical_url,
            "external_id": self.external_id,
            "title": self.title,
            "author_name": self.author_name,
            "author_url": self.author_url,
            "published_at": self.published_at,
            "published_at_raw": self.published_at_raw,
            "published_year": self.published_year,
            "tags": self.tags,
            "categories": self.categories,
            "language": self.language,
            "body_text": self.body_text,
            "attribution_block": self.attribution_block,
            "body_with_attribution": self.body_with_attribution,
            "paragraph_count": self.paragraph_count,
            "word_count": self.word_count,
            "char_count": self.char_count,
            "content_hash": self.content_hash,
            "license_note": self.license_note,
            "source_keywords": self.source_keywords,
            "source_description": self.source_description,
            "detected_ad_placements": self.detected_ad_placements,
            "detected_commercial_links": self.detected_commercial_links,
            "primary_niche": self.primary_niche,
            "target_funnel": self.target_funnel,
            "recommended_affiliate": self.recommended_affiliate,
            "seo_slug": self.seo_slug,
            "flags": self.flags,
            "is_complete": self.is_complete,
            "extra": self.extra,
            "adapter_version": self.adapter_version,
            "http_status": self.http_status,
            "fetched_at": self.fetched_at,
        }


def normalize_terms(values: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values or []:
        if not v:
            continue
        t = " ".join(str(v).split()).strip(" ,;|/").lower()
        if not t or len(t) > 80:
            continue
        if t in {"stories", "story", "home", "all", "categories", "tags", "more"}:
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return sorted(out)


def build_attribution_block(
    *,
    source_url: str,
    site_name: str,
    site_host: str,
    author_name: str | None,
    author_url: str | None,
    published_at: str | None,
    categories: list[str],
    tags: list[str],
    license_note: str,
    archived_at: str,
) -> str:
    def val(v: str | None) -> str:
        return v if v else "not listed on source page"

    lines = [
        f"Source URL: {source_url}",
        f"Source site: {site_name} ({site_host})",
        f"Author/submitter: {val(author_name)}",
        f"Author profile: {val(author_url)}",
        f"Published: {val(published_at)}",
        f"Categories: {', '.join(categories) if categories else 'not listed'}",
        f"Tags: {', '.join(tags) if tags else 'not listed'}",
        f"License/terms: {license_note}",
        f"Archived at: {archived_at}",
    ]
    return ATTRIBUTION_SEPARATOR.lstrip("\n") + "\n".join(lines)


def strip_attribution(body: str) -> str:
    idx = body.find(ATTRIBUTION_SEPARATOR)
    return body if idx == -1 else body[:idx].rstrip()


def build_record(
    parsed: ParsedStory,
    *,
    site_id: str,
    site_name: str,
    site_host: str,
    license_note: str,
    adapter_version: str,
    min_words: int = 120,
) -> StoryRecord:
    tags = normalize_terms(parsed.tags)
    categories = normalize_terms(parsed.categories)
    body_text = "\n\n".join(p for p in parsed.body_paragraphs if p.strip())
    fetched_at = utcnow_iso()
    flags = list(parsed.flags)

    def flag(f: str) -> None:
        if f not in flags:
            flags.append(f)

    if not parsed.title:
        flag(Flag.MISSING_TITLE)
    if not parsed.author_name:
        flag(Flag.MISSING_AUTHOR)
    if not parsed.published_at:
        flag(Flag.UNPARSEABLE_DATE if parsed.published_at_raw else Flag.MISSING_DATE)
    if not tags and not categories:
        flag(Flag.MISSING_TAGS)
    if not parsed.canonical_url:
        flag(Flag.MISSING_CANONICAL)
    if not body_text:
        flag(Flag.EMPTY_BODY)

    wc = word_count(body_text)
    if body_text and wc < min_words:
        flag(Flag.SHORT_BODY)

    attribution = build_attribution_block(
        source_url=parsed.canonical_url or parsed.source_url,
        site_name=site_name,
        site_host=site_host,
        author_name=parsed.author_name,
        author_url=parsed.author_url,
        published_at=parsed.published_at,
        categories=categories,
        tags=tags,
        license_note=license_note,
        archived_at=fetched_at,
    )

    blocking = {Flag.EMPTY_BODY, Flag.MISSING_TITLE, Flag.MISSING_CANONICAL}
    is_complete = not (blocking & set(flags))

    return StoryRecord(
        dedup_key=parsed.dedup_key,
        source_site=site_id,
        source_site_name=site_name,
        source_url=parsed.source_url,
        canonical_url=parsed.canonical_url,
        external_id=parsed.external_id,
        title=parsed.title,
        author_name=parsed.author_name,
        author_url=parsed.author_url,
        published_at=parsed.published_at,
        published_at_raw=parsed.published_at_raw,
        published_year=year_of(parsed.published_at),
        tags=tags,
        categories=categories,
        language=parsed.language,
        body_text=body_text,
        attribution_block=attribution,
        body_with_attribution=(body_text + "\n\n" + attribution)
        if body_text
        else attribution,
        paragraph_count=len([p for p in parsed.body_paragraphs if p.strip()]),
        word_count=wc,
        char_count=len(body_text),
        content_hash=content_hash(parsed.body_paragraphs),
        license_note=license_note,
        source_keywords=parsed.source_keywords,
        source_description=parsed.source_description,
        detected_ad_placements=parsed.detected_ad_placements,
        detected_commercial_links=parsed.detected_commercial_links,
        primary_niche=parsed.primary_niche,
        target_funnel=parsed.target_funnel,
        recommended_affiliate=parsed.recommended_affiliate,
        seo_slug=parsed.seo_slug,
        classification_confidence=parsed.classification_confidence,
        flags=sorted(flags),
        is_complete=is_complete,
        extra=parsed.extra,
        adapter_version=adapter_version,
        http_status=parsed.http_status,
        fetched_at=fetched_at,
    )
