"""
Parser for unit profile pages (``/unit/{slug}``).

Data source: ``__NEXT_DATA__.props.pageProps.entry`` (Contentful ``armyListEntry``).

All unit data — including stat profiles — is present directly on the unit page.
No cross-referencing with the army page is required.

Output nodes: one ``Unit`` node per page.
Output edges:
- ``HAS_RULE``   — unit → each special rule slug extracted from the specialRules field.
- ``BELONGS_TO`` — unit → army slug from armyLists field (if present).
"""

from __future__ import annotations

import logging
import re

from pipeline.constants import EdgeType, NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class UnitParser(BaseParser):
    """Parse a unit profile page (armyListEntry) into a ``Unit`` node."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("UnitParser: ISR fallback or missing data at %s", url)
            return result

        entry = pp.get("entry", {})
        if not entry:
            logger.warning("UnitParser: no entry in pageProps at %s", url)
            return result

        ct = entry.get("sys", {}).get("contentType", {}).get("sys", {}).get("id")
        if ct != "armyListEntry":
            logger.warning("UnitParser: unexpected contentType %r at %s", ct, url)
            return result

        fields = entry.get("fields", {})
        name: str = fields.get("name", "")
        slug: str = fields.get("slug") or self._slug(url)
        date = self._date_only(fetched_at)

        # Stat profiles
        profiles = self._parse_unit_profiles(fields.get("unitProfile", []))

        # Troop type and category are linked entries (lists)
        troop_type_entry = self._first_linked(fields.get("troopType"))
        unit_category_entry = self._first_linked(fields.get("unitCategory"))
        troop_type_slug = troop_type_entry.get("slug") if troop_type_entry else None
        unit_category_slug = unit_category_entry.get("slug") if unit_category_entry else None

        # Army membership — armyLists is a list of linked association entries
        army_slugs = [
            e.get("fields", {}).get("slug")
            for e in (fields.get("armyLists") or [])
            if isinstance(e, dict) and e.get("fields", {}).get("slug")
        ]
        # Use first army for source_citation book name
        army_name = ""
        if army_slugs:
            army_name = (fields.get("armyLists") or [{}])[0].get("fields", {}).get("name", "")

        node = {
            "node_type": NodeType.UNIT,
            "id": slug,
            "url": url,
            "source_citation": self._make_source_citation(army_name or "Unknown Army"),
            "last_updated": date,
            "cost_points_per_model": fields.get("cost"),
            "unit_category_id": unit_category_slug,
            "troop_type_id": troop_type_slug,
            "base_size_mm": self._parse_base_size(fields.get("baseSize", "")),
            "unit_size": self._parse_unit_size(str(fields.get("unitSize", "1"))),
            "profiles": profiles,
            "name": name,
            "i18n": self._make_i18n(name=name),
        }
        result.nodes.append(node)

        # BELONGS_TO edges
        for army_slug in army_slugs:
            result.edges.append(self._make_edge(slug, army_slug, EdgeType.BELONGS_TO))

        # HAS_RULE edges — extract rule names from the specialRules rich text,
        # then resolve to slugs.  We also pick up any linked slugs from
        # association.fields if the rich text has entry-hyperlinks.
        sr_text = self._richtext_to_text(fields.get("specialRules"))
        sr_links = self._richtext_entry_links(fields.get("specialRules"))
        sr_slugs_seen: set[str] = set()

        # From embedded links (most reliable)
        for link_slug in sr_links:
            if link_slug not in sr_slugs_seen:
                result.edges.append(self._make_edge(slug, link_slug, EdgeType.HAS_RULE))
                sr_slugs_seen.add(link_slug)

        # From plain text (fallback: each non-empty line is a rule name)
        if not sr_links and sr_text:
            for rule_name in [line.strip() for line in sr_text.splitlines() if line.strip()]:
                rule_slug = self._name_to_slug(rule_name)
                if rule_slug not in sr_slugs_seen:
                    result.edges.append(self._make_edge(slug, rule_slug, EdgeType.HAS_RULE))
                    sr_slugs_seen.add(rule_slug)

        # HAS_OPTIONAL_RULE edges for optionalRules
        or_links = self._richtext_entry_links(fields.get("optionalRules"))
        for link_slug in or_links:
            result.edges.append(self._make_edge(slug, link_slug, EdgeType.HAS_OPTIONAL_RULE))

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _first_linked(self, val) -> dict | None:
        """Return the ``fields`` dict of the first item in a linked-entry list."""
        if isinstance(val, list) and val:
            return val[0].get("fields")
        if isinstance(val, dict):
            return val.get("fields")
        return None

