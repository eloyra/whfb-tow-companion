"""
Parser for dedicated spell pages (``/spell/{slug}``).

Each page has contentType ``spell`` and carries fully structured fields:
  slug, name, castingValue (int), castingValueOverride (str|None), range, order,
  magicLore (list of lore entries), pageReference, association, body (rich text),
  bodyIndex (pre-flattened text including mechanical rule text).

One ``Spell`` node is emitted per page.

``BELONGS_TO_LORE`` edges are NOT emitted here — lore membership is owned by
``LoreParser`` (standard lores) and the two-pass coordinator (renegade lores).

``REFERENCES`` edges are emitted for every entry-hyperlink in the body rich text
(e.g. enchantment, range-self-spells, start-of-turn, ward-saves) and for the
casting-value rule node when the spell has a casting value.
"""

from __future__ import annotations

import logging

from pipeline.constants import CASTING_VALUE_RULE_ID, EdgeType, NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class SpellParser(BaseParser):
    """Parse a dedicated ``/spell/{slug}`` page into a single ``Spell`` node."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("SpellParser: ISR fallback or missing data at %s", url)
            return result

        entry = pp.get("entry", {})
        fields = entry.get("fields", {})
        name: str = fields.get("name", "")
        slug: str = fields.get("slug") or self._slug(url)
        date = self._date_only(fetched_at)

        if not name or not slug:
            logger.warning("SpellParser: no name/slug at %s", url)
            return result

        # Source citation
        association: list[dict] = fields.get("association") or []
        book = (
            association[0].get("fields", {}).get("name", "Rulebook") if association else "Rulebook"
        )
        page_ref: int | None = fields.get("pageReference")

        # Casting value — numeric or override string (e.g. "Special")
        casting_value_raw = fields.get("castingValue")
        casting_value: int | None = (
            int(casting_value_raw) if casting_value_raw is not None else None
        )
        casting_value_override: str | None = fields.get("castingValueOverride") or None
        if casting_value_override:
            casting_value = None

        order_raw = fields.get("order", 0)
        lore_number: int = int(order_raw) // 10 if order_raw is not None else 0

        # lore_id: hint only; edges are authoritative (BELONGS_TO_LORE from LoreParser / two-pass)
        magic_lore: list[dict] = fields.get("magicLore") or []
        lore_id: str | None = None
        if magic_lore:
            raw_slug: str = magic_lore[0].get("fields", {}).get("slug", "")
            lore_id = raw_slug.removesuffix("-lore") or None

        text = self._body_text(fields)

        # spell_type from rendered DOM (div.spell Type row)
        spell_type = self._extract_spell_type(html)

        node = {
            "node_type": NodeType.SPELL,
            "id": slug,
            "url": url,
            **self._make_source_citation(book, page_ref),
            "last_updated": date,
            "lore_id": lore_id,
            "lore_number": lore_number,
            "casting_value": casting_value,
            "casting_value_override": casting_value_override,
            "casting_value_boosted": None,
            "range": fields.get("range") or None,
            "spell_type": spell_type,
            "duration": None,
            "target": None,
            "name": name,
            "text": text,
            **self._make_i18n(name=name, text=text),
        }
        result.nodes.append(node)

        # REFERENCES edges from body entry-hyperlinks
        for link_slug in self._richtext_entry_links(fields.get("body")):
            if link_slug != slug:
                result.edges.append(self._make_edge(slug, link_slug, EdgeType.REFERENCES))

        # REFERENCES edge to the casting-value rule when casting value is present
        if casting_value is not None or casting_value_override is not None:
            result.edges.append(self._make_edge(slug, CASTING_VALUE_RULE_ID, EdgeType.REFERENCES))

        return result
