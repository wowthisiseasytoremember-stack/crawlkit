"""Layer 3: Weighted configuration-driven taxonomy classifier."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_TAXONOMY_PATH = None  # No default in crawlkit; pass explicitly or use embedded fallback

_EMBEDDED_FALLBACK = {
    "version": 1,
    "weights": {
        "source_tag": 6,
        "meta_keyword": 5,
        "title": 4,
        "body": 1,
        "body_match_cap": 3,
    },
    "categories": [
        {
            "primary_niche": "femboy_gfe_trans",
            "target_funnel": "pod_1_creator_hub",
            "recommended_affiliate": "ai_companion_apps",
            "keywords": [
                "femboy",
                "trans romance",
                "crossdressing",
                "maid",
                "gfe",
                "sissy",
            ],
        },
        {
            "primary_niche": "fantasy_monster_scifi",
            "target_funnel": "pod_2_merch_newsletter",
            "recommended_affiliate": "adult_gaming_visual_novels",
            "keywords": [
                "monster",
                "alien",
                "scifi",
                "fantasy",
                "orc",
                "demon",
                "tentacle",
            ],
        },
        {
            "primary_niche": "kink_power_dynamics",
            "target_funnel": "pod_5_kink_platform",
            "recommended_affiliate": "niche_specialty_retail",
            "keywords": [
                "bdsm",
                "chastity",
                "femdom",
                "submissive",
                "humiliation",
                "authoritarian",
            ],
        },
        {
            "primary_niche": "audio_asmr_scripts",
            "target_funnel": "pod_1_audio_tier",
            "recommended_affiliate": "voice_and_audio",
            "keywords": [
                "asmr",
                "audio script",
                "roleplay script",
                "bedtime whisper",
                "voice script",
            ],
        },
        {
            "primary_niche": "niche_relational_romance",
            "target_funnel": "weekly_syndicate_newsletter",
            "recommended_affiliate": "niche_dating_networks",
            "keywords": [
                "roommate",
                "slow burn",
                "friends to lovers",
                "romance",
                "dating",
                "wife",
                "cheating",
            ],
        },
    ],
}


@dataclass(frozen=True, slots=True)
class TaxonomyCategory:
    primary_niche: str
    target_funnel: str
    recommended_affiliate: str
    keywords: tuple[str, ...]


class StoryClassifier:
    """Weighted, configuration-driven taxonomy classifier.

    Source tags and meta keywords intentionally have higher influence than long-body
    prose. Body term frequency is capped so a repeated word cannot overwhelm
    stronger on-page taxonomy evidence.
    """

    def __init__(self, taxonomy_path: str | Path | None = None) -> None:
        """Load taxonomy config from path, or fall back to embedded default.

        Resolution order:
          1. taxonomy_path (if provided AND file exists)
          2. DEFAULT_TAXONOMY_PATH (if set AND file exists)
          3. Embedded fallback taxonomy
        """
        resolved_path = taxonomy_path if taxonomy_path is not None else DEFAULT_TAXONOMY_PATH
        if resolved_path is not None and Path(resolved_path).exists():
            self.taxonomy_path = Path(resolved_path)
            config = json.loads(self.taxonomy_path.read_text(encoding="utf-8"))
        else:
            self.taxonomy_path = Path(resolved_path) if resolved_path is not None else None
            config = _EMBEDDED_FALLBACK

        self.weights: dict[str, int] = {
            key: int(value) for key, value in config.get("weights", {}).items()
        }
        self.weights.setdefault("source_tag", 6)
        self.weights.setdefault("meta_keyword", 5)
        self.weights.setdefault("title", 4)
        self.weights.setdefault("body", 1)
        self.weights.setdefault("body_match_cap", 3)
        self.categories = tuple(
            TaxonomyCategory(
                primary_niche=item["primary_niche"],
                target_funnel=item["target_funnel"],
                recommended_affiliate=item["recommended_affiliate"],
                keywords=tuple(item.get("keywords", [])),
            )
            for item in config["categories"]
        )

    @staticmethod
    def _normalize(value: str) -> str:
        value = unicodedata.normalize("NFKC", value).casefold()
        value = re.sub(r"[\u2010-\u2015_/]+", " ", value)
        value = re.sub(r"[^\w\s'-]", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    @classmethod
    def _term_count(cls, haystack: str, term: str) -> int:
        normalized_term = cls._normalize(term)
        if not normalized_term:
            return 0
        pattern = r"(?<!\w)" + re.escape(normalized_term) + r"(?!\w)"
        return len(re.findall(pattern, haystack))

    @staticmethod
    def slugify(value: str) -> str:
        ascii_value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
        return slug or "untitled"

    def classify_fields(
        self,
        title: str | None,
        tags: list[str],
        categories: list[str],
        keywords: list[str],
        body_sample: str,
    ) -> dict[str, Any]:
        norm_title = self._normalize(title or "")
        norm_body = self._normalize(body_sample[:4000])
        norm_tags = [self._normalize(t) for t in (tags + categories)]
        norm_keywords = [self._normalize(k) for k in keywords]

        scores: dict[str, int] = {}
        matched_by_category: dict[str, list[str]] = {}
        first_slug_term: dict[str, str] = {}

        for category in self.categories:
            score = 0
            matches: list[str] = []
            for keyword in category.keywords:
                normalized_keyword = self._normalize(keyword)
                if not normalized_keyword:
                    continue

                tag_hit = any(
                    self._term_count(tag, normalized_keyword) > 0 for tag in norm_tags
                )
                if tag_hit:
                    score += self.weights["source_tag"]
                    matches.append(f"tag:{keyword}")
                    first_slug_term.setdefault(
                        category.primary_niche, normalized_keyword
                    )

                keyword_hit = any(
                    self._term_count(meta, normalized_keyword) > 0
                    for meta in norm_keywords
                )
                if keyword_hit:
                    score += self.weights["meta_keyword"]
                    matches.append(f"keyword:{keyword}")
                    first_slug_term.setdefault(
                        category.primary_niche, normalized_keyword
                    )

                title_count = self._term_count(norm_title, normalized_keyword)
                if title_count:
                    score += self.weights["title"] * min(title_count, 2)
                    matches.append(f"title:{keyword}")
                    first_slug_term.setdefault(
                        category.primary_niche, normalized_keyword
                    )

                body_count = self._term_count(norm_body, normalized_keyword)
                if body_count:
                    capped = min(body_count, self.weights["body_match_cap"])
                    score += self.weights["body"] * capped
                    matches.append(f"body:{keyword}x{capped}")
                    first_slug_term.setdefault(
                        category.primary_niche, normalized_keyword
                    )

            if score > 0:
                scores[category.primary_niche] = score
                matched_by_category[category.primary_niche] = matches

        if not scores:
            # Fallback to default romance
            return {
                "primary_niche": "niche_relational_romance",
                "target_funnel": "weekly_syndicate_newsletter",
                "recommended_affiliate": "niche_dating_networks",
                "seo_slug": f"{self.slugify(title or 'story')}-niche_relational_romance",
                "scores": {},
                "matched_terms": [],
                "confidence": 0.0,
            }

        best_niche = max(scores, key=lambda key: scores[key])
        best_category = next(
            c for c in self.categories if c.primary_niche == best_niche
        )
        slug_seed = first_slug_term.get(best_niche, best_niche)
        seo_slug = f"{self.slugify(title or 'story')}-{self.slugify(slug_seed)}"

        # Calculate confidence: best_score / (best_score + second_best_score + epsilon)
        sorted_scores = sorted(scores.values(), reverse=True)
        best_score = sorted_scores[0]
        second_best = sorted_scores[1] if len(sorted_scores) > 1 else 0
        epsilon = 1e-6
        confidence = best_score / (best_score + second_best + epsilon)

        return {
            "primary_niche": best_category.primary_niche,
            "target_funnel": best_category.target_funnel,
            "recommended_affiliate": best_category.recommended_affiliate,
            "seo_slug": seo_slug,
            "scores": scores,
            "matched_terms": matched_by_category.get(best_niche, []),
            "confidence": round(confidence, 4),
        }


def classify_story(
    title: str | None,
    tags: list[str],
    categories: list[str],
    body_sample: str,
    keywords: list[str] | None = None,
    taxonomy_path: str | Path | None = None,
) -> dict[str, Any]:
    return StoryClassifier(taxonomy_path=taxonomy_path).classify_fields(
        title, tags, categories, keywords or [], body_sample
    )
