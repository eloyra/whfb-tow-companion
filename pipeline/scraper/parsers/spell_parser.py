"""
Parser for lore-of-magic pages (``/the-lores-of-magic/{slug}``).

Content type: ``rule`` with ``ruleType[0].fields.slug == "the-lores-of-magic"``.

Individual spells are **not** separate pages on the wiki.  They are embedded
inside the lore page body as Contentful ``embedded-entry-block`` nodes.  Each
block's ``data.spell`` key holds an array of spell objects.

Data source: ``__NEXT_DATA__.props.pageProps.entry`` (Contentful ``rule``).
Spell data: ``entry.fields.body`` → embedded-entry-block → ``data.spell[]``.

Each spell object in the array has:
- ``name``                 (str)      display name
- ``slug``                 (str)      canonical id
- ``order``                (int)      position in the lore (0 = signature spell)
- ``castingValue``         (int|null) numeric casting target
- ``castingValueOverride`` (str|null) e.g. "Special" — replaces numeric value
- ``range``                (str|null) e.g. ``"48\\"``
- ``type``                 (str|null) spell type (Magic Missile, Hex, etc.)
- ``description``          (richtext) short flavour / summary text
- ``body``                 (richtext) full rules text

Output nodes: multiple ``Spell`` nodes per lore page (one per spell entry).
Output edges: none (spells reference their lore via the ``lore_id`` attribute).
"""

from __future__ import annotations

import logging

from pipeline.constants import NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class SpellParser(BaseParser):
    """Parse a lore-of-magic page into multiple ``Spell`` nodes."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("SpellParser: ISR fallback or missing data at %s", url)
            return result

        entry = pp.get("entry", {})
        fields = entry.get("fields", {})
        lore_name: str = fields.get("name", "")
        lore_slug: str = fields.get("slug") or self._slug(url)
        date = self._date_only(fetched_at)

        if not lore_name:
            logger.warning("SpellParser: no name field at %s", url)
            return result

        association: list[dict] = fields.get("association") or []
        book = association[0].get("fields", {}).get("name", "Rulebook") if association else "Rulebook"

        # Spells are embedded in the body as embedded-entry-block nodes.
        # Each block has data.spell = [spell_object, ...]
        embedded_blocks = self._richtext_find_embedded_blocks(fields.get("body"))
        spells_found = 0

        for block in embedded_blocks:
            spell_list = block.get("data", {}).get("spell")
            if not isinstance(spell_list, list):
                continue
            for spell_entry in spell_list:
                # Each entry is a Contentful object: {fields: {...}, sys: {...}}
                spell_data = spell_entry.get("fields", {}) if isinstance(spell_entry, dict) else {}
                node = self._parse_spell(spell_data, lore_slug, url, date, book)
                if node:
                    result.nodes.append(node)
                    spells_found += 1

        if spells_found == 0:
            logger.warning("SpellParser: no spells found in embedded blocks at %s", url)

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_spell(
        self,
        data: dict,
        lore_slug: str,
        url: str,
        date: str,
        book: str,
    ) -> dict | None:
        name: str = data.get("name", "")
        slug: str = data.get("slug") or self._name_to_slug(name)
        if not name or not slug:
            return None

        # castingValueOverride (e.g. "Special") takes precedence; when present,
        # the numeric castingValue is not meaningful for display.
        casting_value: int | None = data.get("castingValue")
        casting_value_override: str | None = data.get("castingValueOverride") or None
        if casting_value_override:
            casting_value = None

        description_text = self._richtext_to_text(data.get("description"))
        body_text = self._richtext_to_text(data.get("body"))
        text = description_text or body_text

        return {
            "node_type": NodeType.SPELL,
            "id": slug,
            "url": url,
            "source_citation": self._make_source_citation(book),
            "last_updated": date,
            "lore_id": lore_slug,
            "order": data.get("order"),
            "casting_value": casting_value,
            "casting_value_override": casting_value_override,
            "range": data.get("range") or None,
            "spell_type": data.get("type") or None,
            "name": name,
            "text": text,
            "i18n": self._make_i18n(name=name, text=text),
        }
