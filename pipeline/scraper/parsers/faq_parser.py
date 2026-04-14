"""
Parser for the FAQ page (``/faq``).

Unlike most pages on this wiki, the FAQ page does **not** use a single
``entry`` key in ``pageProps``.  Instead, ``pageProps.entries`` is a flat
array of FAQ entry objects, one per Q&A pair.

Data source: ``__NEXT_DATA__.props.pageProps.entries[]`` (Contentful entries).

Each entry's ``fields`` object contains:
- ``question``  (str)      the question text
- ``body``      (richtext) the answer text
- ``source``    (str)      attribution, e.g.
                           "Official Warhammer: The Old World FAQ & Errata –
                            Version 1.5.2"
- ``slug``      (str)      canonical id for this Q&A pair

The FAQ version is extracted from the ``source`` field with a regex.

Output nodes: one ``FAQ`` node per entry in the ``entries`` array.
Output edges:
- ``CLARIFIES`` — FAQ → rule slug, for every entry-hyperlink in the answer
  body that resolves to a linked rule or spell entry.
"""

from __future__ import annotations

import logging
import re

from pipeline.constants import EdgeType, NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)

_SOURCE_VERSION_RE = re.compile(r"Version\s+([\d.]+)", re.IGNORECASE)


class FAQParser(BaseParser):
    """Parse the /faq page into multiple ``FAQ`` nodes."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("FAQParser: ISR fallback or missing data at %s", url)
            return result

        entries: list[dict] = pp.get("entries") or []
        date = self._date_only(fetched_at)

        if not entries:
            logger.warning("FAQParser: no entries array in pageProps at %s", url)
            return result

        for idx, entry in enumerate(entries):
            fields = entry.get("fields", {})
            question: str = fields.get("question", "")
            slug: str = fields.get("slug", "")
            source: str = fields.get("source", "")

            answer_text = self._richtext_to_text(fields.get("body"))

            if not slug:
                slug = self._name_to_slug(question[:60]) or f"faq-{idx}"

            version = _extract_version(source)
            book = f"FAQ {version}" if version else "FAQ"

            node = {
                "node_type": NodeType.FAQ,
                "id": slug,
                "url": url,
                "source_citation": self._make_source_citation(book),
                "last_updated": date,
                "question": question,
                "answer": answer_text,
                "i18n": {
                    "en": {"question": question, "answer": answer_text},
                    "es": {},
                },
            }
            result.nodes.append(node)

            # CLARIFIES edges — linked rule/spell entries in the answer body
            for link_slug in self._richtext_entry_links(fields.get("body")):
                result.edges.append(self._make_edge(slug, link_slug, EdgeType.CLARIFIES))

        return result


def _extract_version(source: str) -> str | None:
    m = _SOURCE_VERSION_RE.search(source)
    return m.group(1) if m else None
