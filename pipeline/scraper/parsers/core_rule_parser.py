"""
Parser for core rulebook mechanic pages.

Content type: ``rule`` with ``ruleType[0].fields.slug`` set to a section slug
such as ``movement-in-detail``, ``magic-in-detail``, ``shooting-in-detail``,
etc.  These pages cover core gameplay mechanics — they are **not** special
rules, weapons, spells, or magic items.

Data source: ``__NEXT_DATA__.props.pageProps.entry`` (Contentful ``rule``).
Navigation context: ``pageProps.prev`` and ``pageProps.next`` linked entries.

Output nodes: one ``CoreRule`` node per page.
Output edges:
- ``PART_OF_SECTION`` — page slug → section slug
- ``REFERENCES``      — for entry-hyperlinks embedded in the rule body
"""

from __future__ import annotations

import logging

from pipeline.constants import EdgeType, NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class CoreRuleParser(BaseParser):
    """Parse a core rulebook mechanics page into a ``CoreRule`` node."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("CoreRuleParser: ISR fallback or missing data at %s", url)
            return result

        entry = pp.get("entry", {})
        fields = entry.get("fields", {})
        name: str = fields.get("name", "")
        slug: str = fields.get("slug") or self._slug(url)
        date = self._date_only(fetched_at)

        if not name:
            logger.warning("CoreRuleParser: no name field at %s", url)
            return result

        body_text = self._richtext_to_text(fields.get("body"))
        description = self._richtext_to_text(fields.get("description")) or ""
        text = body_text or description

        page_ref: int | None = fields.get("pageReference")

        # Section comes from ruleType[0].fields.slug (e.g. "movement-in-detail")
        rule_types: list[dict] = fields.get("ruleType") or []
        section_slug = ""
        if rule_types:
            section_slug = rule_types[0].get("fields", {}).get("slug", "")
        if not section_slug:
            # Fall back to URL path segments (uses urlparse to avoid splitting the domain).
            # /movement-in-detail           → section = "movement-in-detail" (this IS the section)
            # /movement-in-detail/fly       → section = "movement-in-detail" (parent segment)
            from urllib.parse import urlparse as _urlparse
            path_parts = [p for p in _urlparse(url).path.strip("/").split("/") if p]
            if len(path_parts) >= 2:
                section_slug = path_parts[-2]
            elif len(path_parts) == 1:
                section_slug = path_parts[0]

        section_name = section_slug.replace("-", " ").title()

        # Prev/next page navigation from pageProps
        prev_entry = pp.get("prev") or {}
        next_entry = pp.get("next") or {}
        prev_slug = (
            prev_entry.get("fields", {}).get("slug")
            if isinstance(prev_entry, dict)
            else None
        )
        next_slug = (
            next_entry.get("fields", {}).get("slug")
            if isinstance(next_entry, dict)
            else None
        )
        prev_page_url = f"/{section_slug}/{prev_slug}" if (prev_slug and section_slug) else None
        next_page_url = f"/{section_slug}/{next_slug}" if (next_slug and section_slug) else None

        node = {
            "node_type": NodeType.CORE_RULE,
            "id": slug,
            "url": url,
            "source_citation": self._make_source_citation("Rulebook", page_ref),
            "last_updated": date,
            "section": section_name,
            "section_id": section_slug,
            "prev_page_url": prev_page_url,
            "next_page_url": next_page_url,
            "name": name,
            "text": text,
            "i18n": self._make_i18n(name=name, text=text),
        }
        result.nodes.append(node)

        # PART_OF_SECTION edge to the parent section node
        if section_slug:
            result.edges.append(self._make_edge(slug, section_slug, EdgeType.PART_OF_SECTION))

        # REFERENCES edges for linked entries embedded in the rule body
        for link_slug in self._richtext_entry_links(fields.get("body")):
            if link_slug != slug:
                result.edges.append(self._make_edge(slug, link_slug, EdgeType.REFERENCES))

        return result
