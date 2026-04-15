"""
Parser for lore-of-magic pages (``/the-lores-of-magic/{slug}``).

Content type: ``rule`` with ``ruleType[0].fields.slug == "the-lores-of-magic"``.

Individual spells are **not** separate pages on the wiki.  Two encoding formats
exist depending on whether the lore is a standard lore or a "renegade" variant:

**Standard lores** embed spells as Contentful ``embedded-entry-block`` nodes
inside the body.  Each block's ``data.spell`` key holds an array of spell objects.

**Renegade lores** (e.g. ``lore-of-naggaroth-renegade``) do not use embedded
blocks.  Spells are encoded directly in rich text as a repeating sequence of:
``heading-2`` (spell name) → ``table`` (Type / Casting Value / Range rows) →
one or more ``paragraph`` nodes (body text), separated by ``hr`` nodes.

Data source: ``__NEXT_DATA__.props.pageProps.entry`` (Contentful ``rule``).

Standard spell object fields (embedded format):
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
import re

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
        body = fields.get("body")

        # Strategy 1: standard lores — spells in embedded-entry-block nodes.
        embedded_blocks = self._richtext_find_embedded_blocks(body)
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

        # Strategy 2: renegade lores — spells encoded as richtext heading-2/table/paragraph.
        if spells_found == 0:
            for node in self._parse_spells_from_richtext(body, lore_slug, url, date, book):
                result.nodes.append(node)
                spells_found += 1

        if spells_found == 0:
            logger.warning("SpellParser: no spells found at %s", url)

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_spells_from_richtext(
        self,
        body: dict | None,
        lore_slug: str,
        url: str,
        date: str,
        book: str,
    ) -> list[dict]:
        """Parse spells from renegade lore pages where spells are encoded as rich text.

        The pattern per spell is:
            heading-2  → spell name
            table      → stat rows (Type, Casting Value, Range, …)
            paragraph+ → body text
        Spells are separated by ``hr`` nodes.  Leading intro paragraphs are skipped.
        """
        if not isinstance(body, dict):
            return []

        content = body.get("content", [])
        spells: list[dict] = []
        order = 0
        i = 0

        while i < len(content):
            node = content[i]
            if node.get("nodeType") != "heading-2":
                i += 1
                continue

            name = self._richtext_to_text(node).strip()
            i += 1

            # Optional table with spell stats immediately after the heading.
            stats: dict[str, str] = {}
            if i < len(content) and content[i].get("nodeType") == "table":
                stats = self._parse_spell_stat_table(content[i])
                i += 1

            # Collect body paragraphs until the next heading-2, hr, or end.
            body_parts: list[str] = []
            while i < len(content) and content[i].get("nodeType") not in ("heading-2", "hr"):
                text_chunk = self._richtext_to_text(content[i]).strip()
                if text_chunk:
                    body_parts.append(text_chunk)
                i += 1
            # Skip the hr separator if present.
            if i < len(content) and content[i].get("nodeType") == "hr":
                i += 1

            spell_text = "\n".join(body_parts)
            slug = self._name_to_slug(name)
            if not name or not slug:
                continue

            casting_value, casting_value_override = self._parse_casting_value(
                stats.get("Casting Value", "")
            )

            spells.append({
                "node_type": NodeType.SPELL,
                "id": slug,
                "url": url,
                "source_citation": self._make_source_citation(book),
                "last_updated": date,
                "lore_id": lore_slug,
                "order": order,
                "casting_value": casting_value,
                "casting_value_override": casting_value_override,
                "range": stats.get("Range") or None,
                "spell_type": stats.get("Type") or None,
                "name": name,
                "text": spell_text,
                "i18n": self._make_i18n(name=name, text=spell_text),
            })
            order += 1

        return spells

    def _parse_spell_stat_table(self, table_node: dict) -> dict[str, str]:
        """Extract key-value pairs from a spell stats table."""
        result: dict[str, str] = {}
        for row in table_node.get("content", []):
            if row.get("nodeType") != "table-row":
                continue
            cells = row.get("content", [])
            if len(cells) < 2:
                continue
            key = self._richtext_to_text(cells[0]).strip()
            value = self._richtext_to_text(cells[1]).strip()
            if key:
                result[key] = value
        return result

    def _parse_casting_value(self, raw: str) -> tuple[int | None, str | None]:
        """Parse a casting value string into ``(int_value, override_string)``.

        Returns ``(None, raw)`` when the value is non-numeric (e.g. "Special").
        Returns ``(int, None)`` for normal numeric values like ``"7+"`` or ``"9+"``.
        """
        raw = raw.strip()
        if not raw:
            return None, None
        m = re.match(r"^(\d+)", raw)
        if m:
            return int(m.group(1)), None
        return None, raw

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
        body_text = self._body_text(data)
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
