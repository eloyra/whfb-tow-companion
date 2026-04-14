"""
Parser for army index pages (``/army/{slug}``).

Data source: ``__NEXT_DATA__.props.pageProps`` (Contentful ``association`` entry
plus pre-computed ``rulesByType`` and ``unitsByType`` arrays).

Output nodes: one ``Army`` node per page.
Output edges:
- ``BELONGS_TO``   — unit → army (one per unit found in unitsByType)
- ``HAS_RULE``     — army → rule slug  (from Special Rules and Weapons of War sections)
- ``USES_LORE``    — army → lore slug  (from The Lores of Magic section)
- ``CAN_TAKE_ITEM``— army → magic items page slug (from Magic Items section)

Note: Unit stat profiles (M/WS/BS/…) are also available on individual unit
pages, which is the canonical source used by :class:`UnitParser`.  This parser
does NOT produce ``unit_profile`` records because the unit parser already
handles them completely.
"""

from __future__ import annotations

import logging

from pipeline.constants import EdgeType, NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)

# Mapping from rulesByType section slug to EdgeType
_SECTION_EDGE: dict[str, str] = {
    "special-rules":            EdgeType.HAS_RULE,
    "weapons-of-war":           EdgeType.HAS_WEAPON,
    "the-lores-of-magic":       EdgeType.USES_LORE,
    "magic-items":              EdgeType.CAN_TAKE_ITEM,
    "magic-items-and-abilities": EdgeType.CAN_TAKE_ITEM,
}


class ArmyParser(BaseParser):
    """Parse an army index page into an ``Army`` node plus structural edges."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("ArmyParser: ISR fallback or missing data at %s", url)
            return result

        entry = pp.get("entry", {})
        if not entry:
            logger.warning("ArmyParser: no entry in pageProps at %s", url)
            return result

        ct = entry.get("sys", {}).get("contentType", {}).get("sys", {}).get("id")
        if ct != "association":
            logger.warning("ArmyParser: unexpected contentType %r at %s", ct, url)
            return result

        fields = entry.get("fields", {})
        army_name: str = fields.get("name", "")
        army_slug: str = fields.get("slug") or self._slug(url)
        date = self._date_only(fetched_at)

        army_node = {
            "node_type": NodeType.ARMY,
            "id": army_slug,
            "url": url,
            "source_citation": self._make_source_citation(army_name),
            "last_updated": date,
            "name": army_name,
            "i18n": self._make_i18n(name=army_name),
        }
        result.nodes.append(army_node)

        # --- Rules by type: emit HAS_RULE / HAS_WEAPON / USES_LORE / CAN_TAKE_ITEM ---
        rules_by_type: list[dict] = pp.get("rulesByType", [])
        for section in rules_by_type:
            section_slug: str = section.get("fields", {}).get("slug", "")
            edge_type = _SECTION_EDGE.get(section_slug)
            if edge_type is None:
                continue
            for rule_entry in section.get("rules", []):
                rule_slug = rule_entry.get("fields", {}).get("slug")
                if rule_slug:
                    result.edges.append(self._make_edge(army_slug, rule_slug, edge_type))

        # --- Units by type: emit BELONGS_TO edges ---
        units_by_type: list[dict] = pp.get("unitsByType", [])
        for section in units_by_type:
            for unit_entry in section.get("units", []):
                unit_slug = unit_entry.get("fields", {}).get("slug")
                if unit_slug:
                    result.edges.append(
                        self._make_edge(unit_slug, army_slug, EdgeType.BELONGS_TO)
                    )

        return result
