"""
Parser for magic item list pages (``/magic-items/{slug}``).

Content type: ``rule`` with ``ruleType[0].fields.slug`` matching ``magic-items``
or ``magic-items-and-abilities``.

Individual magic items are **not** separate pages.  They are embedded inside
the list-page body as Contentful ``embedded-entry-block`` nodes.  Each block's
``data.magicItem`` key holds an array of item objects.

Data source: ``__NEXT_DATA__.props.pageProps.entry`` (Contentful ``rule``).
Item data: ``entry.fields.body`` → embedded-entry-block → ``data.magicItem[]``.

Each magic item object in the array has:
- ``name``        (str)      display name
- ``slug``        (str)      canonical id
- ``cost``        (int|null) points cost
- ``type``        (str|null) item category (e.g. "Magic Weapon", "Talisman")
- ``description`` (richtext) short summary text
- ``body``        (richtext) full rules text

``army_id`` is derived from ``entry.fields.association[0].fields.slug`` when
the association is not the generic ``"rulebook"`` entry — indicating an
army-specific items page (e.g. Vampire Counts vampiric powers).

Output nodes: multiple ``MagicItem`` nodes per page.
Output edges: none.
"""

from __future__ import annotations

import logging

from pipeline.constants import MAGIC_ITEM_TYPE_MAP, NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)  # used for ISR/missing-name warnings above


class MagicItemParser(BaseParser):
    """Parse a magic items page into multiple ``MagicItem`` nodes."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("MagicItemParser: ISR fallback or missing data at %s", url)
            return result

        entry = pp.get("entry", {})
        fields = entry.get("fields", {})
        page_name: str = fields.get("name", "")
        date = self._date_only(fetched_at)

        if not page_name:
            logger.warning("MagicItemParser: no name field at %s", url)
            return result

        # Determine army_id and book name from association
        association: list[dict] = fields.get("association") or []
        army_id: str | None = None
        book = "Rulebook"
        if association:
            assoc_fields = association[0].get("fields", {})
            assoc_slug: str = assoc_fields.get("slug", "")
            assoc_name: str = assoc_fields.get("name", "Rulebook")
            if assoc_slug and assoc_slug != "rulebook":
                army_id = assoc_slug
                book = assoc_name
            else:
                book = assoc_name

        # Magic items are embedded in the body as embedded-entry-block nodes.
        # Each block has data.magicItem = [item_object, ...]
        embedded_blocks = self._richtext_find_embedded_blocks(fields.get("body"))

        for block in embedded_blocks:
            item_list = block.get("data", {}).get("magicItem")
            if not isinstance(item_list, list):
                continue
            for item_entry in item_list:
                # Each entry is a Contentful object: {fields: {...}, sys: {...}}
                item_data = item_entry.get("fields", {}) if isinstance(item_entry, dict) else {}
                node = self._parse_item(item_data, url, date, book, army_id)
                if node:
                    result.nodes.append(node)

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_item(
        self,
        data: dict,
        url: str,
        date: str,
        book: str,
        army_id: str | None,
    ) -> dict | None:
        name: str = data.get("name", "")
        slug: str = data.get("slug") or self._name_to_slug(name)
        if not name or not slug:
            return None

        description_text = self._richtext_to_text(data.get("description"))
        body_text = self._body_text(data)
        text = description_text or body_text

        raw_type: str = data.get("type") or ""
        item_type: str | None = MAGIC_ITEM_TYPE_MAP.get(raw_type) or (
            raw_type.lower().replace(" ", "_") if raw_type else None
        )

        # costOverride is a text field (e.g. "Special") that supersedes the numeric cost.
        cost: int | None = data.get("cost")
        if data.get("costOverride"):
            cost = None

        return {
            "node_type": NodeType.MAGIC_ITEM,
            "id": slug,
            "url": url,
            "source_citation": self._make_source_citation(book),
            "last_updated": date,
            "item_type": item_type,
            "points_cost": cost,
            "army_id": army_id,
            "is_single_use": None,  # not present in Contentful data model
            "name": name,
            "text": text,
            "i18n": self._make_i18n(name=name, text=text),
        }
