"""
Parser for lore-of-magic pages (``/the-lores-of-magic/{slug}``).

Produces:
- One ``Lore`` node (name, description, source citation).
- ``BELONGS_TO_LORE`` edges from each spell slug to this lore.

Spell nodes themselves are now built from their dedicated ``/spell/{slug}`` pages
(``SpellParser``), not from this lore page.  This parser's only job for spells is to
enumerate which slugs belong to the lore so the edges can be written.

For **standard lores** the canonical spell slugs come from the embedded-entry-block
``spell[].fields.slug`` values in the Contentful JSON — exact matches against the
dedicated-page ids.

For **renegade lores** (no structured slug list) the coordinator handles membership via a
two-pass name-match after all parsers run; this parser emits zero ``BELONGS_TO_LORE`` edges
and the two-pass fills them in.
"""

from __future__ import annotations

import logging

from pipeline.constants import EdgeType, NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class LoreParser(BaseParser):
    """Parse a lore-of-magic page into a ``Lore`` node and ``BELONGS_TO_LORE`` edges."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("LoreParser: ISR fallback or missing data at %s", url)
            return result

        entry = pp.get("entry", {})
        fields = entry.get("fields", {})
        lore_name: str = fields.get("name", "")
        lore_slug: str = fields.get("slug") or self._slug(url)
        date = self._date_only(fetched_at)

        if not lore_name:
            logger.warning("LoreParser: no name field at %s", url)
            return result

        association: list[dict] = fields.get("association") or []
        book = (
            association[0].get("fields", {}).get("name", "Rulebook") if association else "Rulebook"
        )
        page_ref: int | None = fields.get("pageReference")

        # Use bodyIndex (full content) for text; fall back to description for standard lores
        # whose description is a human-readable summary. bodyIndex includes spell names in
        # renegade lores, which enables the two-pass renegade membership derivation.
        description = self._richtext_to_text(fields.get("description")) or ""
        body_text = self._body_text(fields)
        lore_text = body_text or description
        lore_node = {
            "node_type": NodeType.LORE,
            "id": lore_slug,
            "url": url,
            **self._make_source_citation(book, page_ref),
            "last_updated": date,
            "name": lore_name,
            "text": lore_text,
            **self._make_i18n(name=lore_name, text=lore_text),
        }
        result.nodes.append(lore_node)

        # Emit BELONGS_TO_LORE for standard lores using the embedded spell slugs.
        body = fields.get("body")
        embedded_blocks = self._richtext_find_embedded_blocks(body)
        for block in embedded_blocks:
            spell_list = block.get("data", {}).get("spell")
            if not isinstance(spell_list, list):
                continue
            for spell_entry in spell_list:
                spell_data = spell_entry.get("fields", {}) if isinstance(spell_entry, dict) else {}
                slug = spell_data.get("slug") or self._name_to_slug(spell_data.get("name", ""))
                if slug:
                    result.edges.append(self._make_edge(slug, lore_slug, EdgeType.BELONGS_TO_LORE))

        return result
