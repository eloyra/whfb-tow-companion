"""
Parser for weapons-of-war pages (``/weapons-of-war/{slug}``).

Content type: ``rule`` with ``ruleType[0].fields.slug == "weapons-of-war"``.
Routing to this parser is handled by ``parsers/__init__.py`` based on URL
pattern — the ``rule`` content type is shared with special rules, core rules,
spells, and magic items.

Data source: ``__NEXT_DATA__.props.pageProps.entry`` (Contentful ``rule``).

Output nodes: one ``Weapon`` node per page.
Output edges:
- ``REFERENCES`` — for entry-hyperlinks embedded in the weapon body text.

``weapon_class`` is inferred from keyword matching in the combined slug, name,
and body text.  Ordering matters: armour/shield keywords take priority over
missile and melee to avoid misclassifying "sword and shield" as melee first.
"""

from __future__ import annotations

import logging
import re

from pipeline.constants import EdgeType, NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)

# Slugs that are unambiguously armour/equipment regardless of text keywords.
_ARMOUR_SLUGS: frozenset[str] = frozenset(
    {
        "light-armour",
        "heavy-armour",
        "full-plate-armour",
        "dragon-armour",
        "chaos-armour",
        "gromril-armour",
        "ithilmar-armour",
        "shield",
        "buckler",
        "barding",
        "dragon-scale-helm",
        "helmet",
    }
)

# Slugs that are unambiguously war machines (missile profile but special class).
_WAR_MACHINE_SLUGS: frozenset[str] = frozenset(
    {
        "cannon",
        "mortar",
        "rock-lobber",
        "bolt-thrower",
        "stone-thrower",
        "hellblaster-volley-gun",
        "steam-tank",
        "organ-gun",
    }
)

# Keyword → weapon_class mapping (checked in order; first match wins).
# Armour/shield keywords intentionally removed — they match too broadly on
# weapon descriptions (e.g. "ignores armour saves", "sword and shield").
_CLASS_HINTS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"\bmissile\b|\bbow\b|\bcrossbow\b|\bpistol\b|\brifle\b|\bthrown\b|\bblowpipe\b", re.I
        ),
        "missile",
    ),
    (
        re.compile(
            r"\bsword\b|\baxe\b|\bhalberd\b|\blance\b|\bspear\b|\bflail\b|\bmace\b|\bhammer\b|\bgreat.weapon\b|\bweapon\b",
            re.I,
        ),
        "melee",
    ),
    (re.compile(r"\barmou?r\b|\bshield\b|\bhelmet\b|\bmail\b|\bbarding\b", re.I), "armour"),
]


def _infer_weapon_class(slug: str, name: str, text: str) -> str:
    if slug in _ARMOUR_SLUGS:
        return "armour"
    if slug in _WAR_MACHINE_SLUGS:
        return "war_machine"
    combined = (slug + " " + name).lower()  # name+slug only — text is too noisy
    for pattern, cls in _CLASS_HINTS:
        if pattern.search(combined):
            return cls
    return "equipment"


class WeaponParser(BaseParser):
    """Parse a weapons-of-war page into a single ``Weapon`` node."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("WeaponParser: ISR fallback or missing data at %s", url)
            return result

        entry = pp.get("entry", {})
        fields = entry.get("fields", {})
        name: str = fields.get("name", "")
        slug: str = fields.get("slug") or self._slug(url)
        date = self._date_only(fetched_at)

        if not name:
            logger.warning("WeaponParser: no name field at %s", url)
            return result

        body_text = self._body_text(fields)
        description = self._richtext_to_text(fields.get("description")) or ""
        text = body_text or description

        page_ref: int | None = fields.get("pageReference")
        association: list[dict] = fields.get("association") or []
        book = (
            association[0].get("fields", {}).get("name", "Rulebook") if association else "Rulebook"
        )

        weapon_class = _infer_weapon_class(slug, name, text)

        profile = self._extract_weapon_profile(html)

        node = {
            "node_type": NodeType.WEAPON,
            "id": slug,
            "url": url,
            **self._make_source_citation(book, page_ref),
            "last_updated": date,
            "weapon_class": weapon_class,
            "range": profile["range"],
            "strength": profile["strength"],
            "ap": profile["ap"],
            "special_rules": profile["special_rules"],
            "armour_value": None,
            "shots": None,
            "template_type": None,
            "is_indirect": None,
            "bounce": None,
            "name": name,
            "text": text,
            **self._make_i18n(name=name, text=text),
        }
        result.nodes.append(node)

        # REFERENCES edges for linked entries in the weapon body
        for link_slug in self._richtext_entry_links(fields.get("body")):
            if link_slug != slug:
                result.edges.append(self._make_edge(slug, link_slug, EdgeType.REFERENCES))

        return result
