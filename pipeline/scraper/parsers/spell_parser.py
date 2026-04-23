"""
Parser for lore-of-magic pages (``/the-lores-of-magic/{slug}``).

Each lore page produces:
- One ``Lore`` node from the page-level entry (name, description, page reference).
- Multiple ``Spell`` nodes — one per spell embedded in the page body.
- ``BELONGS_TO_LORE`` edges from each spell to its lore.

Two spell encoding formats exist on the wiki:

**Standard lores** embed spells as Contentful ``embedded-entry-block`` nodes.
Each block's ``data.spell`` array holds spell objects with fields:
  name, slug, order (0/10/20/…/70), castingValue, castingValueOverride,
  range, type ('Signature Spell' | '1'…'6'), description, body.

**Renegade lores** (e.g. ``lore-of-naggaroth-renegade``) encode spells directly
in rich text as: ``heading-2`` (name) → ``table`` (stat rows) →
``paragraph(s)`` (body text), separated by ``hr`` nodes.

``lore_number`` is derived from the Contentful ``order`` field (order // 10),
giving 0 for the signature spell and 1–N for numbered spells.

``spell_type`` (Hex, Magic Missile, etc.) is NOT present in the Contentful data
model — it is set to ``null`` and can be enriched via text parsing in a later
pipeline stage.

Data source: ``__NEXT_DATA__.props.pageProps.entry`` (Contentful ``rule``).
"""

from __future__ import annotations

import logging
import re

from pipeline.constants import EdgeType, NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class SpellParser(BaseParser):
    """Parse a lore-of-magic page into a ``Lore`` node and multiple ``Spell`` nodes."""

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
        book = (
            association[0].get("fields", {}).get("name", "Rulebook") if association else "Rulebook"
        )
        page_ref: int | None = fields.get("pageReference")

        # Emit Lore node from the page-level entry.
        lore_description = self._richtext_to_text(fields.get("description")) or ""
        lore_node = {
            "node_type": NodeType.LORE,
            "id": lore_slug,
            "url": url,
            "source_citation": self._make_source_citation(book, page_ref),
            "last_updated": date,
            "name": lore_name,
            "text": lore_description,
            "i18n": self._make_i18n(name=lore_name, text=lore_description),
        }
        result.nodes.append(lore_node)

        body = fields.get("body")
        spells_found = 0

        # Strategy 1: standard lores — spells in embedded-entry-block nodes.
        embedded_blocks = self._richtext_find_embedded_blocks(body)
        for block in embedded_blocks:
            spell_list = block.get("data", {}).get("spell")
            if not isinstance(spell_list, list):
                continue
            for spell_entry in spell_list:
                spell_data = spell_entry.get("fields", {}) if isinstance(spell_entry, dict) else {}
                node = self._build_spell_node(spell_data, lore_slug, url, date, book)
                if node:
                    result.nodes.append(node)
                    result.edges.append(
                        self._make_edge(node["id"], lore_slug, EdgeType.BELONGS_TO_LORE)
                    )
                    spells_found += 1

        # Strategy 2: renegade lores — spells as richtext heading-2/table/paragraph.
        if spells_found == 0:
            for node in self._parse_spells_from_richtext(body, lore_slug, url, date, book):
                result.nodes.append(node)
                result.edges.append(
                    self._make_edge(node["id"], lore_slug, EdgeType.BELONGS_TO_LORE)
                )
                spells_found += 1

        if spells_found == 0:
            logger.warning("SpellParser: no spells found at %s", url)

        return result

    # ------------------------------------------------------------------
    # Spell node builders
    # ------------------------------------------------------------------

    def _build_spell_node(
        self,
        data: dict,
        lore_slug: str,
        url: str,
        date: str,
        book: str,
    ) -> dict | None:
        """Build a Spell node from a Contentful embedded spell object."""
        name: str = data.get("name", "")
        slug: str = data.get("slug") or self._name_to_slug(name)
        if not name or not slug:
            return None

        # lore_number: derived from the ``order`` field (multiples of 10).
        # order=0 → signature spell (lore_number=0); order=10 → spell 1, etc.
        order_raw = data.get("order", 0)
        lore_number: int = int(order_raw) // 10 if order_raw is not None else 0

        # castingValueOverride (e.g. "Special") supersedes the numeric value.
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
            "lore_number": lore_number,
            "casting_value": casting_value,
            "casting_value_override": casting_value_override,
            "casting_value_boosted": None,  # not in Contentful data model
            "range": data.get("range") or None,
            "spell_type": None,  # not in Contentful; enriched in later stage
            "duration": None,  # not in Contentful
            "target": None,  # not in Contentful
            "name": name,
            "text": text,
            "i18n": self._make_i18n(name=name, text=text),
        }

    def _parse_spells_from_richtext(
        self,
        body: dict | None,
        lore_slug: str,
        url: str,
        date: str,
        book: str,
    ) -> list[dict]:
        """Parse spells from renegade lore pages (richtext heading-2/table/paragraph format)."""
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

            stats: dict[str, str] = {}
            if i < len(content) and content[i].get("nodeType") == "table":
                stats = self._parse_spell_stat_table(content[i])
                i += 1

            body_parts: list[str] = []
            while i < len(content) and content[i].get("nodeType") not in ("heading-2", "hr"):
                chunk = self._richtext_to_text(content[i]).strip()
                if chunk:
                    body_parts.append(chunk)
                i += 1
            if i < len(content) and content[i].get("nodeType") == "hr":
                i += 1

            spell_text = "\n".join(body_parts)
            slug = self._name_to_slug(name)
            if not name or not slug:
                continue

            casting_value, casting_value_override = self._parse_casting_value(
                stats.get("Casting Value", "")
            )

            spells.append(
                {
                    "node_type": NodeType.SPELL,
                    "id": slug,
                    "url": url,
                    "source_citation": self._make_source_citation(book),
                    "last_updated": date,
                    "lore_id": lore_slug,
                    "lore_number": order,
                    "casting_value": casting_value,
                    "casting_value_override": casting_value_override,
                    "casting_value_boosted": None,
                    "range": stats.get("Range") or None,
                    "spell_type": None,
                    "duration": None,
                    "target": None,
                    "name": name,
                    "text": spell_text,
                    "i18n": self._make_i18n(name=name, text=spell_text),
                }
            )
            order += 1

        return spells

    def _parse_spell_stat_table(self, table_node: dict) -> dict[str, str]:
        """Extract key→value pairs from a spell stats table node."""
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
        """Parse ``"7+"`` → ``(7, None)``; ``"Special"`` → ``(None, "Special")``."""
        raw = raw.strip()
        if not raw:
            return None, None
        m = re.match(r"^(\d+)", raw)
        if m:
            return int(m.group(1)), None
        return None, raw
