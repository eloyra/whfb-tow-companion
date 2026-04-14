"""
Abstract base class for all HTML parsers in the scraper layer.

The website (tow.whfb.app) is a Next.js + Contentful CMS application.
ALL page data is embedded as JSON in a ``<script id="__NEXT_DATA__">`` tag in
the HTML source.  Parsers extract that JSON; they do NOT traverse the HTML DOM.

Every concrete parser inherits from ``BaseParser`` and implements ``parse()``,
which receives raw HTML, the canonical URL, and the crawl timestamp, and
returns a ``ParseResult`` containing lists of node dicts and edge dicts.

Node dicts must include a ``"node_type"`` key used by the coordinator to route
them to the correct output file.  Edge dicts must include ``"src"``, ``"dst"``,
and ``"relation"`` keys.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Regex that extracts the JSON payload from the Next.js __NEXT_DATA__ script tag.
_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class ParseResult:
    """Container for the nodes and edges produced by a single parser invocation."""

    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)

    def merge(self, other: "ParseResult") -> None:
        """Merge *other* into this result in-place."""
        self.nodes.extend(other.nodes)
        self.edges.extend(other.edges)


# ---------------------------------------------------------------------------
# Base parser
# ---------------------------------------------------------------------------


class BaseParser(ABC):
    """Abstract base for all page parsers.

    The primary helper is :meth:`_extract_next_data`, which returns the
    ``pageProps`` dict from the ``__NEXT_DATA__`` JSON.  If the page is still
    in ISR fallback state (``isFallback: true``), it returns ``None`` so
    callers can skip the page; the crawler is responsible for retrying it.
    """

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        """Parse *html* from *url* and return structured nodes and edges.

        Args:
            html: Raw HTML text of the page.
            url: Canonical URL of the page.
            fetched_at: ISO-8601 timestamp string recorded by the crawler.

        Returns:
            A :class:`ParseResult` with zero or more nodes and edges.
        """

    # ------------------------------------------------------------------
    # __NEXT_DATA__ extraction
    # ------------------------------------------------------------------

    def _extract_next_data(self, html: str) -> dict | None:
        """Extract and decode the ``pageProps`` from the Next.js data blob.

        Returns ``None`` if:
        - The script tag is not found.
        - ``isFallback`` is ``True`` (page not yet pre-rendered by ISR).
        """
        m = _NEXT_DATA_RE.search(html)
        if not m:
            logger.warning("__NEXT_DATA__ script tag not found")
            return None
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse __NEXT_DATA__ JSON: %s", exc)
            return None
        if data.get("isFallback"):
            return None
        return data.get("props", {}).get("pageProps", {})

    # ------------------------------------------------------------------
    # Contentful rich-text helpers
    # ------------------------------------------------------------------

    def _richtext_to_text(self, node: dict | None) -> str:
        """Recursively extract plain text from a Contentful rich-text document."""
        if not isinstance(node, dict):
            return ""
        if node.get("nodeType") == "text":
            return node.get("value", "")
        return "".join(
            self._richtext_to_text(child) for child in node.get("content", [])
        )

    def _richtext_find_embedded_blocks(self, node: dict | None) -> list[dict]:
        """Return all ``embedded-entry-block`` nodes from a rich-text document."""
        if not isinstance(node, dict):
            return []
        results: list[dict] = []
        if node.get("nodeType") == "embedded-entry-block":
            results.append(node)
        for child in node.get("content", []):
            results.extend(self._richtext_find_embedded_blocks(child))
        return results

    # ------------------------------------------------------------------
    # Stat value parsing
    # ------------------------------------------------------------------

    def _stat_value(self, raw: str) -> int | None:
        """Convert a profile stat string to ``int | None``.

        Handles:
        - ``"-"`` / ``"–"`` / empty → ``None``
        - ``"(+N)"`` bonus values (mount composites) → ``None``
        - Digit strings → ``int``
        """
        if not isinstance(raw, str):
            return int(raw) if isinstance(raw, int) else None
        raw = raw.strip()
        if raw in ("-", "–", "—", ""):
            return None
        if raw.startswith("("):
            return None  # composite mount bonus — not an absolute value
        try:
            return int(raw)
        except ValueError:
            return None

    def _parse_unit_profiles(self, profile_list: list[dict]) -> list[dict]:
        """Convert raw Contentful unitProfile array to schema-compliant profile dicts."""
        profiles: list[dict] = []
        stat_keys = ["M", "WS", "BS", "S", "T", "W", "I", "A", "Ld"]
        for raw in profile_list:
            profile: dict = {"name": raw.get("Name", "")}
            for key in stat_keys:
                profile[key] = self._stat_value(raw.get(key, "-"))
            profiles.append(profile)
        return profiles

    # ------------------------------------------------------------------
    # Unit-size / base-size helpers
    # ------------------------------------------------------------------

    def _parse_base_size(self, raw: str) -> dict | None:
        """Parse ``'30 x 60 mm'`` → ``{'width': 30, 'depth': 60}``."""
        m = re.search(r"(\d+)\s*[xX×]\s*(\d+)", raw)
        if m:
            return {"width": int(m.group(1)), "depth": int(m.group(2))}
        return None

    def _parse_unit_size(self, raw: str) -> dict:
        """Parse unit size string into ``{'min': int, 'max': int | None}``.

        Examples: ``'5+'`` → ``{min:5, max:None}``, ``'20-40'`` → ``{min:20, max:40}``,
        ``'1'`` → ``{min:1, max:1}``.
        """
        raw = str(raw).strip()
        # Range: "20-40" or "20–40"
        m_range = re.search(r"(\d+)\s*[-–—]\s*(\d+)", raw)
        if m_range:
            return {"min": int(m_range.group(1)), "max": int(m_range.group(2))}
        # Single value with optional "+": "5+" or "1"
        m_single = re.search(r"(\d+)(\+)?", raw)
        if m_single:
            val = int(m_single.group(1))
            has_plus = bool(m_single.group(2))
            return {"min": val, "max": None if has_plus else val}
        return {"min": 1, "max": None}

    # ------------------------------------------------------------------
    # Schema helpers
    # ------------------------------------------------------------------

    def _make_i18n(self, *, name: str, text: str | None = None) -> dict:
        """Build a minimal i18n dict with English canonical values.

        Spanish translations are added in the ``pipeline.i18n`` stage.
        """
        en: dict = {"name": name}
        if text is not None:
            en["text"] = text
        return {"en": en, "es": {}}

    def _make_edge(
        self, src: str, dst: str, relation: str, properties: dict | None = None
    ) -> dict:
        return {"src": src, "dst": dst, "relation": relation, "properties": properties or {}}

    def _make_source_citation(self, book: str, page: int | None = None) -> dict:
        return {"book": book, "page": page}

    def _date_only(self, fetched_at: str) -> str:
        """Return just the date portion of an ISO-8601 timestamp."""
        return fetched_at[:10]

    def _slug(self, url: str) -> str:
        from urllib.parse import urlparse
        path = urlparse(url).path.strip("/")
        return path.split("/")[-1] if path else "unknown"

    def _name_to_slug(self, name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    def _richtext_entry_links(self, node: dict | None) -> list[str]:
        """Return slugs from all entry-hyperlink / embedded-entry-inline nodes."""
        if not isinstance(node, dict):
            return []
        results: list[str] = []
        if node.get("nodeType") in ("entry-hyperlink", "embedded-entry-inline"):
            target = node.get("data", {}).get("target", {})
            slug = target.get("fields", {}).get("slug")
            if slug:
                results.append(slug)
        for child in node.get("content", []):
            results.extend(self._richtext_entry_links(child))
        return results
