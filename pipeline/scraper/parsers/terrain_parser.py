"""
Parser for battlefield terrain wiki pages.

Emits one :Terrain node per page.  Edges (TERRAIN_INTERACTION) are written
later by ``seed_terrain_interactions()`` in the graph builder.

Data source: ``__NEXT_DATA__.props.pageProps.entry`` (Contentful ``rule``).
Defensively checks ``ruleType[0].fields.slug == "battlefield-terrain"``.
"""

from __future__ import annotations

import logging
import re

from pipeline.constants import NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slug -> terrain_class mapping derived from the schema catalogue.
# Unknown slugs fall back to body-text heuristic scanning.
# ---------------------------------------------------------------------------

_TERRAIN_CLASS_BY_SLUG: dict[str, str] = {
    "open-ground": "open",
    "difficult-terrain": "difficult",
    "dangerous-terrain": "dangerous",
    "impassable-terrain": "impassable",
    "low-linear-obstacles": "low_linear_obstacle",
    "defended-low-linear-obstacles": "low_linear_obstacle",
    "high-linear-obstacles": "high_linear_obstacle",
    "woods": "woods",
    "woodland-boundaries": "woods",
    "arboreal-gloom": "woods",
    "hills": "hills",
    "vantage-point": "hills",
    "beyond-the-crest": "hills",
    "arcane-monolith": "special_feature",
    "monument-of-glory": "special_feature",
    "dark-ruins": "special_feature",
    "tower": "building",
    "buildings": "building",
    "linear-terrain-features": "linear_terrain_feature",
}

# Override for blocks_movement to avoid false positives on pages that mention
# "impassable" in a conditional context (e.g. woods).
_BLOCKS_MOVEMENT_BY_SLUG: dict[str, bool] = {
    "open-ground": False,
    "difficult-terrain": False,
    "dangerous-terrain": False,
    "impassable-terrain": True,
    "low-linear-obstacles": False,
    "defended-low-linear-obstacles": False,
    "high-linear-obstacles": True,
    "woods": False,
    "woodland-boundaries": False,
    "arboreal-gloom": False,
    "hills": False,
    "vantage-point": False,
    "beyond-the-crest": False,
    "arcane-monolith": True,
    "monument-of-glory": True,
    "dark-ruins": True,
    "tower": True,
    "buildings": True,
    "linear-terrain-features": False,
}

# Keywords scanned in body text when the slug is not in the map above.
_TERRAIN_CLASS_KEYWORDS: list[tuple[str, str]] = [
    ("open ground", "open"),
    ("difficult terrain", "difficult"),
    ("very difficult terrain", "difficult"),
    ("dangerous terrain", "dangerous"),
    ("impassable terrain", "impassable"),
    ("low linear obstacle", "low_linear_obstacle"),
    ("high linear obstacle", "high_linear_obstacle"),
    ("woods", "woods"),
    ("forest", "woods"),
    ("hills", "hills"),
    ("building", "building"),
    ("special feature", "special_feature"),
    ("linear terrain feature", "linear_terrain_feature"),
]

# ---------------------------------------------------------------------------
# Heuristic regexes (case-insensitive)
# ---------------------------------------------------------------------------

_BLOCKS_MOVEMENT_RE = re.compile(r"\bimpassable\b", re.IGNORECASE)
_REQUIRES_DANGEROUS_TEST_RE = re.compile(
    r"\b(dangerous terrain test|take a dangerous terrain test)\b", re.IGNORECASE
)
_DISRUPTS_UNITS_RE = re.compile(r"\b(disrupted|cannot claim (a |any )?rank bonus)\b", re.IGNORECASE)
_GRANTS_COVER_RE = re.compile(r"\b(soft cover|hard cover)\b", re.IGNORECASE)
_MOVEMENT_PENALTY_RE = re.compile(
    r"\b(half(ed)?|halve|moves at half|treat as difficult)\b", re.IGNORECASE
)


class TerrainParser(BaseParser):
    """Parse a battlefield-terrain wiki page into a single :Terrain node."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("TerrainParser: ISR fallback or missing data at %s", url)
            return result

        entry = pp.get("entry", {})
        fields = entry.get("fields", {})
        name: str = fields.get("name", "")
        slug: str = fields.get("slug") or self._slug(url)
        date = self._date_only(fetched_at)

        if not name:
            logger.warning("TerrainParser: no name field at %s", url)
            return result

        # Defensive check — bail out if this is not actually a terrain page.
        rule_type_entries: list[dict] = fields.get("ruleType") or []
        if not rule_type_entries:
            logger.warning("TerrainParser: missing ruleType at %s", url)
            return result
        rt_slug = rule_type_entries[0].get("fields", {}).get("slug", "")
        if rt_slug != "battlefield-terrain":
            logger.warning(
                "TerrainParser: ruleType slug '%s' != 'battlefield-terrain' at %s",
                rt_slug,
                url,
            )
            return result

        body_text = self._body_text(fields)
        page_ref: int | None = fields.get("pageReference")
        association: list[dict] = fields.get("association") or []
        book = (
            association[0].get("fields", {}).get("name", "Rulebook") if association else "Rulebook"
        )

        terrain_class = self._derive_terrain_class(slug, body_text)
        blocks_movement = (
            _BLOCKS_MOVEMENT_BY_SLUG[slug]
            if slug in _BLOCKS_MOVEMENT_BY_SLUG
            else bool(_BLOCKS_MOVEMENT_RE.search(body_text))
        )
        requires_dangerous_test = bool(_REQUIRES_DANGEROUS_TEST_RE.search(body_text))
        disrupts_units = bool(_DISRUPTS_UNITS_RE.search(body_text))
        grants_cover = self._derive_grants_cover(body_text)
        movement_penalty = self._derive_movement_penalty(body_text)
        special_feature_benefit = body_text if terrain_class == "special_feature" else None

        node = {
            "node_type": NodeType.TERRAIN,
            "id": slug,
            "url": url,
            **self._make_source_citation(book, page_ref),
            "last_updated": date,
            "terrain_class": terrain_class,
            "movement_penalty": movement_penalty,
            "blocks_movement": blocks_movement,
            "disrupts_units": disrupts_units,
            "requires_dangerous_test": requires_dangerous_test,
            "grants_cover": grants_cover,
            "special_feature_benefit": special_feature_benefit,
            "name": name,
            "text": body_text,
            **self._make_i18n(name=name, text=body_text),
        }
        result.nodes.append(node)
        return result

    # ------------------------------------------------------------------
    # Heuristic helpers
    # ------------------------------------------------------------------

    def _derive_terrain_class(self, slug: str, body_text: str) -> str | None:
        """Return the canonical terrain_class for *slug*, falling back to body scan."""
        if slug in _TERRAIN_CLASS_BY_SLUG:
            return _TERRAIN_CLASS_BY_SLUG[slug]

        # Fallback: scan first paragraph / heading (first 500 chars) for keywords.
        sample = body_text[:500].lower()
        for keyword, cls in _TERRAIN_CLASS_KEYWORDS:
            if keyword in sample:
                return cls
        return None

    def _derive_grants_cover(self, body_text: str) -> str | None:
        """Return 'partial' or 'full' if cover is mentioned, else None."""
        m = _GRANTS_COVER_RE.search(body_text)
        if not m:
            return None
        raw = m.group(1).lower()
        if raw == "soft cover":
            return "partial"
        if raw == "hard cover":
            return "full"
        return None

    def _derive_movement_penalty(self, body_text: str) -> str | None:
        """Return a short movement-penalty phrase if matched, else None."""
        m = _MOVEMENT_PENALTY_RE.search(body_text)
        return m.group(0) if m else None
