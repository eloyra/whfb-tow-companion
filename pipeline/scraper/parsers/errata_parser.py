"""
Parser for the errata page (``/errata``).

Like the FAQ page, the errata page uses ``pageProps.entries`` (a flat array)
rather than a single ``pageProps.entry``.

Data source: ``__NEXT_DATA__.props.pageProps.entries[]`` (Contentful entries).

Each entry's ``fields`` object contains:
- ``name``    (str)      heading in the format ``"Page N – Rule Name"``
- ``body``    (richtext) the corrected / amended text
- ``source``  (str)      attribution, e.g.
                         "Official Warhammer: The Old World FAQ & Errata –
                          Version 1.5.2"
- ``slug``    (str)      canonical id for this errata entry

The ``rule_name`` stored on the node is extracted from the ``name`` field by
stripping the leading page-number reference.

Output nodes: one ``Errata`` node per entry in the ``entries`` array.
Output edges:
- ``AMENDS`` — errata → rule slug, for every entry-hyperlink in the corrected
  body that resolves to a linked rule entry.
"""

from __future__ import annotations

import logging
import re

from pipeline.constants import EdgeType, NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)

_SOURCE_VERSION_RE = re.compile(r"Version\s+([\d.]+)", re.IGNORECASE)
# Matches "Page 47 – Fear", "Page 47 - Fear", etc.
_PAGE_PREFIX_RE = re.compile(r"^Page\s+\d+\s*[-–—]\s*", re.IGNORECASE)


class ErrataParser(BaseParser):
    """Parse the /errata page into multiple ``Errata`` nodes."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("ErrataParser: ISR fallback or missing data at %s", url)
            return result

        entries: list[dict] = pp.get("entries") or []
        date = self._date_only(fetched_at)

        if not entries:
            logger.warning("ErrataParser: no entries array in pageProps at %s", url)
            return result

        for idx, entry in enumerate(entries):
            fields = entry.get("fields", {})
            raw_name: str = fields.get("name", "")
            slug: str = fields.get("slug", "")
            source: str = fields.get("source", "")

            corrected_text = self._richtext_to_text(fields.get("body"))

            if not slug:
                slug = self._name_to_slug(raw_name[:60]) or f"errata-{idx:03d}"

            rule_name = _PAGE_PREFIX_RE.sub("", raw_name).strip()

            version = _extract_version(source)
            book = f"Errata {version}" if version else "Errata"

            node = {
                "node_type": NodeType.ERRATA,
                "id": slug,
                "url": url,
                "source_citation": self._make_source_citation(book),
                "last_updated": date,
                "rule_name": rule_name,
                "original_text": "",
                "corrected_text": corrected_text,
                "i18n": {
                    "en": {
                        "original_text": "",
                        "corrected_text": corrected_text,
                    },
                    "es": {},
                },
            }
            result.nodes.append(node)

            # AMENDS edges — linked rule entries in the correction body
            for link_slug in self._richtext_entry_links(fields.get("body")):
                result.edges.append(self._make_edge(slug, link_slug, EdgeType.AMENDS))

        return result


def _extract_version(source: str) -> str | None:
    m = _SOURCE_VERSION_RE.search(source)
    return m.group(1) if m else None
