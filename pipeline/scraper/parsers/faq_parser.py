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

_SOURCE_RE = re.compile(r"^(.*?)\s*[-–—]\s*Version\s+([\d.]+)", re.IGNORECASE)


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

        # Derive topic from URL path suffix: /faq/general-principles → "General Principles"
        url_path = url.rstrip("/")
        topic: str | None = None
        if "/faq/" in url_path:
            suffix = url_path.split("/faq/")[-1]
            if suffix:
                topic = suffix.replace("-", " ").title()

        for idx, entry in enumerate(entries):
            fields = entry.get("fields", {})
            question: str = fields.get("question", "")
            slug: str = fields.get("slug", "")
            source: str = fields.get("source", "")

            answer_text = self._body_text(fields)

            if not slug:
                slug = self._name_to_slug(question[:60]) or f"faq-{idx}"

            source_document, version = _parse_source(source)
            book = f"FAQ {version}" if version else "FAQ"

            node = {
                "node_type": NodeType.FAQ,
                "id": slug,
                "url": url,
                **self._make_source_citation(book),
                "last_updated": date,
                "name": question,
                "topic": topic,
                "source_document": source_document,
                "source_version": version,
                "question": question,
                "answer": answer_text,
                **self._make_i18n(name=question),
            }
            result.nodes.append(node)

            # CLARIFIES edges — linked rule/spell entries in the answer body (CMS hyperlinks).
            # In practice most FAQ answers are plain text with no entry-hyperlinks; the
            # coordinator runs a second text-based pass (_derive_clarifies_amends) that fills
            # in the remaining CLARIFIES edges by name matching.
            for link_slug in self._richtext_entry_links(fields.get("body")):
                result.edges.append(self._make_edge(slug, link_slug, EdgeType.CLARIFIES))

        return result


def _parse_source(source: str) -> tuple[str | None, str | None]:
    """Return ``(source_document, version)`` from a Contentful source attribution string."""
    m = _SOURCE_RE.match(source.strip())
    if m:
        return m.group(1).strip() or None, m.group(2).strip()
    return source.strip() or None, None
