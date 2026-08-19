"""HTML -> clean paragraph text, plus hashing/metrics helpers."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from bs4 import BeautifulSoup, NavigableString, Tag

JUNK_SELECTOR = ",".join(
    [
        "script",
        "style",
        "noscript",
        "iframe",
        "svg",
        "form",
        "button",
        "select",
        "textarea",
        "input",
        "video",
        "audio",
        "picture",
        "source",
        "canvas",
        "nav",
        "footer",
        "aside",
        ".ad",
        ".ads",
        ".advert",
        ".advertisement",
        "[id*='banner']",
        "[class*='banner']",
        "[id*='adsense']",
        "[class*='adsbygoogle']",
        "[id*='taboola']",
        ".share",
        ".sharing",
        ".social",
        ".breadcrumb",
        ".breadcrumbs",
        ".pagination",
        ".pager",
        ".paging",
        "#comments",
        ".comments",
        ".comment",
        ".comment-list",
        ".commentlist",
        ".related",
        ".related-stories",
        ".similar",
        ".sidebar",
        "#sidebar",
        ".vote",
        ".voting",
        ".rating-widget",
        ".report",
        ".bookmark",
    ]
)

BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "blockquote",
    "pre",
    "li",
    "ul",
    "ol",
    "table",
    "tr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "figure",
    "figcaption",
    "dd",
    "dt",
    "dl",
    "address",
    "main",
    "header",
}

_WS_RUN = re.compile(r"[ \t\u00a0\u2000-\u200a\u202f\u205f\u3000]+")
_NL_RUN = re.compile(r"\n{2,}")
_WORD_RE = re.compile(r"[\w’'\-]+", re.UNICODE)


def strip_junk(node: Tag) -> Tag:
    for bad in node.select(JUNK_SELECTOR):
        bad.decompose()
    from bs4 import Comment

    for c in node.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    return node


def node_to_paragraphs(node: Tag) -> list[str]:
    node = strip_junk(node)
    for br in node.find_all("br"):
        br.replace_with(NavigableString("\n"))
    for hr in node.find_all("hr"):
        hr.replace_with(NavigableString("\n\n* * *\n\n"))
    for tag in node.find_all(True):
        if tag.name in BLOCK_TAGS:
            tag.insert_before(NavigableString("\n\n"))
            tag.insert_after(NavigableString("\n\n"))
    return normalize_paragraphs(node.get_text())


def normalize_paragraphs(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    paragraphs: list[str] = []
    for raw_par in _NL_RUN.split(text):
        lines = []
        for raw_line in raw_par.split("\n"):
            line = _WS_RUN.sub(" ", raw_line).strip()
            if line:
                lines.append(line)
        if lines:
            paragraphs.append("\n".join(lines))
    return paragraphs


def clean_inline(text: str | None) -> str | None:
    if text is None:
        return None
    out = _WS_RUN.sub(" ", unicodedata.normalize("NFC", text)).strip()
    return out or None


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def content_hash(paragraphs: list[str]) -> str:
    canon = "\n".join(_WS_RUN.sub(" ", p).strip().lower() for p in paragraphs)
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def soup_of(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def link_density(node: Tag) -> float:
    total = len(node.get_text(strip=True))
    if not total:
        return 1.0
    linked = sum(len(a.get_text(strip=True)) for a in node.find_all("a"))
    return linked / total


def find_prose_container(soup: BeautifulSoup, *, min_chars: int = 400) -> Tag | None:
    best: tuple[float, Tag] | None = None
    for cand in soup.find_all(["div", "article", "section", "td", "main"]):
        text = cand.get_text(" ", strip=True)
        if len(text) < min_chars:
            continue
        if link_density(cand) > 0.25:
            continue
        children = [
            c for c in cand.find_all(["div", "article", "section"], recursive=False)
        ]
        child_max = max((len(c.get_text(" ", strip=True)) for c in children), default=0)
        if child_max > 0.9 * len(text):
            continue
        breaks = len(cand.find_all(["p", "br"]))
        score = (
            len(text) * (1.0 + min(breaks, 200) / 200.0) * (1.0 - link_density(cand))
        )
        if best is None or score > best[0]:
            best = (score, cand)
    return best[1] if best else None
