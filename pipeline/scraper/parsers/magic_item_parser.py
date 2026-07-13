"""
Parser for magic item pages: both list pages and dedicated single-item pages.

**List pages** (``/magic-items/{slug}``): content type ``rule`` with
``ruleType[0].fields.slug`` matching ``magic-items`` or
``magic-items-and-abilities``. Individual magic items are embedded inside the
page body as Contentful ``embedded-entry-block`` nodes; each block's
``data.magicItem`` key holds an array of item objects.

Data source: ``__NEXT_DATA__.props.pageProps.entry`` (Contentful ``rule``).
Item data: ``entry.fields.body`` → embedded-entry-block → ``data.magicItem[]``.

**Dedicated pages** (``/magic-item/{slug}``, singular): content type
``magicItem`` directly — ``entry.fields`` *is* the single item's data (same
field shape as one list-page item entry: ``name``, ``slug``, ``cost``,
``type``, ``costOverride``, ``description``, ``body``, ``association``). The
manifest labels these pages ``core_rule`` (no dedicated ``page_type`` bucket
exists for the singular URL), so ``parsers/__init__.py`` routes them here
explicitly by URL prefix — mirroring the ``/spell/`` override for the
identical duplicate-id bug documented in ADR-0006. Before this override
existed, every one of these ~700 pages was parsed by ``CoreRuleParser``
instead, producing a same-id ``CoreRule`` node for every ``MagicItem`` and
making any labelless ``MATCH (n {id: ...})`` property fetch non-deterministic.

Each magic item object (list-embedded or dedicated-page-direct) has:
- ``name``        (str)      display name
- ``slug``        (str)      canonical id
- ``cost``        (int|null) points cost
- ``type``        (str|null) item category (e.g. "Magic Weapon", "Talisman")
- ``description`` (richtext) short summary text
- ``body``        (richtext) full rules text

``army_id`` is derived from ``entry.fields.association[0].fields.slug`` when
the association is not the generic ``"rulebook"`` entry — indicating an
army-specific items page (e.g. Vampire Counts vampiric powers). For dedicated
pages this reads the same ``association`` field directly off the item entry.

Output nodes: one ``MagicItem`` node (dedicated page) or multiple (list page).
Output edges: none.
"""

from __future__ import annotations

import logging

from pipeline.constants import (
    ARCANE_JOURNAL_ASSOCIATION_ARMY_MAP,
    ARCANE_JOURNAL_PAGE_ARMY_OVERRIDES,
    MAGIC_ITEM_TYPE_MAP,
    NodeType,
)
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
        book, army_id = self._book_and_army_id(fields)

        content_type = entry.get("sys", {}).get("contentType", {}).get("sys", {}).get("id")
        if content_type == "magicItem":
            # Dedicated /magic-item/{slug} page: entry.fields IS the one item's
            # data directly, not a list-page body with embedded item blocks.
            node = self._parse_item(fields, url, date, book, army_id)
            if node:
                result.nodes.append(node)
            return result

        # List page: magic items are embedded in the body as
        # embedded-entry-block nodes. Each block has data.magicItem = [item_object, ...]
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

    @staticmethod
    def _book_and_army_id(fields: dict) -> tuple[str, str | None]:
        """Resolve ``(book, army_id)`` from a page's ``association`` field.

        Shared by list pages (page-level ``entry.fields.association``) and
        dedicated single-item pages (item-level ``entry.fields.association``
        — same field, same shape, since a dedicated page's ``entry.fields``
        stands in for one list-page item entry).
        """
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
        return book, army_id

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

        army_id = self._normalize_army_id(army_id, url)

        return {
            "node_type": NodeType.MAGIC_ITEM,
            "id": slug,
            "url": url,
            **self._make_source_citation(book),
            "last_updated": date,
            "item_type": item_type,
            "points_cost": cost,
            "army_id": army_id,
            "is_single_use": None,  # not present in Contentful data model
            "name": name,
            "text": text,
            **self._make_i18n(name=name, text=text),
        }

    def _normalize_army_id(self, army_id: str | None, url: str) -> str | None:
        """Resolve a raw association slug to a real ``:Army.id`` when known.

        Arcane Journal supplement pages associate with the *book*, not the
        army, so the raw Contentful slug rarely matches an ``:Army.id``
        directly. Page-slug overrides take priority over the association-slug
        map since some Arcane Journal books cover more than one army.
        """
        if army_id is None:
            return None
        page_slug = url.rstrip("/").rsplit("/", 1)[-1]
        if page_slug in ARCANE_JOURNAL_PAGE_ARMY_OVERRIDES:
            return ARCANE_JOURNAL_PAGE_ARMY_OVERRIDES[page_slug]
        return ARCANE_JOURNAL_ASSOCIATION_ARMY_MAP.get(army_id, army_id)
