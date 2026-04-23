"""
Parser for all pages backed by the Contentful ``rule`` content type.

This covers (distinguished by ``entry.fields.ruleType[0].fields.slug``):
- ``special-rules``              → ``SpecialRule`` node
- ``troop-types-in-detail``      → ``TroopType`` node
- ``weapons-of-war``             → ``Weapon`` node  (delegated to WeaponParser)
- ``magic-items*``               → ``MagicItem`` nodes (delegated to MagicItemParser)
- ``the-lores-of-magic``         → ``Spell`` nodes (delegated to SpellParser)
- anything else                  → ``CoreRule`` node (delegated to CoreRuleParser)

Data source: ``__NEXT_DATA__.props.pageProps.entry`` (Contentful ``rule``).

This file only handles ``SpecialRule`` and ``TroopType``.  All other ``rule``-typed
pages are dispatched by the ``parsers/__init__.py`` coordinator to their
dedicated parsers based on URL pattern, which is more reliable than
content-type inspection at runtime.
"""

from __future__ import annotations

import logging

from pipeline.constants import TROOP_TYPE_SEED, EdgeType, NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)

# ruleType slugs that map to Rule nodes vs TroopType nodes
_RULE_TYPE_SLUG = "special-rules"
_TROOP_TYPE_SLUG = "troop-types-in-detail"

# Broad TroopType category inferred from the slug
_CATEGORY_HINTS: dict[str, str] = {
    "infantry": "infantry",
    "cavalry": "cavalry",
    "monstrous": "monster",
    "monster": "monster",
    "war-machine": "war_machine",
    "chariot": "chariot",
    "swarm": "swarm",
    "flyer": "flyer",
    "beast": "beast",
}


def _infer_category(slug: str, name: str) -> str:
    combined = (slug + " " + name).lower()
    for keyword, category in _CATEGORY_HINTS.items():
        if keyword in combined:
            return category
    return "unknown"


def _rule_scope(association: list[dict]) -> tuple[str, str | None]:
    """Return (rule_scope, army_id) based on association list."""
    if not association:
        return "universal", None
    assoc_slug = association[0].get("fields", {}).get("slug", "")
    if assoc_slug and assoc_slug != "rulebook":
        return "army", assoc_slug
    return "universal", None


class RuleParser(BaseParser):
    """Parse a special-rule or troop-type wiki page into a single node."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("RuleParser: ISR fallback or missing data at %s", url)
            return result

        entry = pp.get("entry", {})
        fields = entry.get("fields", {})
        name: str = fields.get("name", "")
        slug: str = fields.get("slug") or self._slug(url)
        date = self._date_only(fetched_at)

        if not name:
            logger.warning("RuleParser: no name field at %s", url)
            return result

        body_text = self._body_text(fields)
        description = self._richtext_to_text(fields.get("description")) or ""
        text = body_text or description

        page_ref: int | None = fields.get("pageReference")
        association: list[dict] = fields.get("association") or []
        book = (
            association[0].get("fields", {}).get("name", "Rulebook") if association else "Rulebook"
        )

        is_troop_type = "/troop-types-in-detail/" in url

        if is_troop_type:
            seed = TROOP_TYPE_SEED.get(slug, {})
            node = {
                "node_type": NodeType.TROOP_TYPE,
                "id": slug,
                "url": url,
                "source_citation": self._make_source_citation(book, page_ref),
                "last_updated": date,
                "category": _infer_category(slug, name),
                "min_models_for_rank_bonus": seed.get("min_models_for_rank_bonus"),
                "max_rank_bonus": seed.get("max_rank_bonus"),
                "unit_strength_per_model": seed.get("unit_strength_per_model"),
                "name": name,
                "text": text,
                "i18n": self._make_i18n(name=name, text=text),
            }
        else:
            rule_scope, army_id = _rule_scope(association)
            node = {
                "node_type": NodeType.SPECIAL_RULE,
                "id": slug,
                "url": url,
                "source_citation": self._make_source_citation(book, page_ref),
                "last_updated": date,
                "rule_scope": rule_scope,
                "army_id": army_id,
                "name": name,
                "text": text,
                "i18n": self._make_i18n(name=name, text=text),
            }
        result.nodes.append(node)

        # REFERENCES edges for linked entries in the rule body
        for link_slug in self._richtext_entry_links(fields.get("body")):
            if link_slug != slug:
                result.edges.append(self._make_edge(slug, link_slug, EdgeType.REFERENCES))

        return result
