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

from bs4 import BeautifulSoup

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
        """Recursively extract plain text from a Contentful rich-text document.

        Handles ``embedded-entry-block`` nodes by descending into the embedded
        entry's fields: prefers the pre-computed ``bodyIndex`` string, then falls
        back to recursing into ``richText`` or ``body``.  This ensures that
        Contentful ``chart`` entries (tables) embedded in a body are not silently
        dropped.
        """
        if not isinstance(node, dict):
            return ""
        if node.get("nodeType") == "text":
            return node.get("value", "")
        if node.get("nodeType") == "embedded-entry-block":
            target_fields = node.get("data", {}).get("target", {}).get("fields", {})
            body_index: str = target_fields.get("bodyIndex", "")
            if body_index:
                return body_index
            # Fall back to the richText or body subtree of the embedded entry.
            subtree = target_fields.get("richText") or target_fields.get("body")
            return self._richtext_to_text(subtree)
        return "".join(self._richtext_to_text(child) for child in node.get("content", []))

    def _body_text(self, fields: dict, key: str = "body") -> str:
        """Return the plain-text content for a Contentful entry's body field.

        Prefers the pre-computed ``bodyIndex`` string on *fields* (which already
        includes flattened table/chart content) and falls back to
        :meth:`_richtext_to_text` on the rich-text tree at *key*.
        """
        body_index: str = fields.get("bodyIndex", "")
        if body_index:
            return body_index
        return self._richtext_to_text(fields.get(key))

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

    def _parse_base_size(self, raw: str) -> dict:
        """Parse ``'30 x 60 mm'`` → ``{'base_width_mm': 30, 'base_depth_mm': 60}``.

        Returns ``{'base_width_mm': None, 'base_depth_mm': None}`` when raw does not
        match.  Always returns a flat dict safe for ``**`` spreading into a node record.
        """
        m = re.search(r"(\d+)\s*[xX×]\s*(\d+)", raw)
        if m:
            return {"base_width_mm": int(m.group(1)), "base_depth_mm": int(m.group(2))}
        return {"base_width_mm": None, "base_depth_mm": None}

    def _parse_unit_size(self, raw: str) -> dict:
        """Parse unit size string into ``{'unit_size_min': int, 'unit_size_max': int | None}``.

        Examples: ``'5+'`` → ``{min:5, max:None}``, ``'20-40'`` → ``{min:20, max:40}``,
        ``'1'`` → ``{min:1, max:1}``.
        Always returns a flat dict safe for ``**`` spreading into a node record.
        """
        raw = str(raw).strip()
        # Range: "20-40" or "20–40"
        m_range = re.search(r"(\d+)\s*[-–—]\s*(\d+)", raw)
        if m_range:
            return {"unit_size_min": int(m_range.group(1)), "unit_size_max": int(m_range.group(2))}
        # Single value with optional "+": "5+" or "1"
        m_single = re.search(r"(\d+)(\+)?", raw)
        if m_single:
            val = int(m_single.group(1))
            has_plus = bool(m_single.group(2))
            return {"unit_size_min": val, "unit_size_max": None if has_plus else val}
        return {"unit_size_min": 1, "unit_size_max": None}

    # ------------------------------------------------------------------
    # Schema helpers
    # ------------------------------------------------------------------

    def _make_i18n(self, *, name: str, text: str | None = None) -> dict:
        """Return per-language translation scalars to spread into a node dict.

        English fields are canonical and live at the top level of the node record.
        Only non-English translations are returned here (e.g. ``name_es``, ``text_es``).
        Until the translate stage populates them, Spanish dicts are empty, so this
        returns ``{}``.  Spread with ``**self._make_i18n(...)`` in node constructors.
        """
        return {}

    def _make_edge(self, src: str, dst: str, relation: str, properties: dict | None = None) -> dict:
        return {"src": src, "dst": dst, "relation": relation, "properties": properties or {}}

    def _make_source_citation(self, book: str, page: int | None = None) -> dict:
        """Return flattened source-citation scalars to spread into a node dict.

        Returns ``{'source_citation_book': book, 'source_citation_page': page}``.
        Neo4j does not support map-typed node properties; this keeps all fields scalar.
        """
        return {"source_citation_book": book, "source_citation_page": page}

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
        return [slug for slug, _ in self._richtext_entry_links_typed(node)]

    # ------------------------------------------------------------------
    # Rendered-DOM helpers (HTML pivot)
    # ------------------------------------------------------------------

    _DASH_VALUES: frozenset[str] = frozenset({"-", "–", "—", ""})

    def _extract_weapon_profile(self, html: str) -> dict:
        """Extract Range/Strength/AP/Special Rules from the rendered weapon profile table.

        Returns a dict with keys ``range``, ``strength``, ``ap``, ``special_rules``.
        Falls back gracefully to null/empty when the table is absent (ISR shell, armour pages,
        war-machine-only pages, etc.) — never raises.
        """
        empty: dict = {"range": None, "strength": None, "ap": None, "special_rules": []}
        try:
            soup = BeautifulSoup(html, "html.parser")
            table = soup.select_one("table.profile-table--weapon")
            if table is None:
                return empty
            rows = table.select("tbody tr")
            if not rows:
                return empty
            cells = rows[0].select("td")
            if len(cells) < 4:
                return empty

            def _norm(cell) -> str | None:
                v = cell.get_text(strip=True)
                return None if v in self._DASH_VALUES else v

            sr_cell = cells[3]
            special_rules = [
                a["href"].rstrip("/").split("/")[-1]
                for a in sr_cell.select('a[href^="/special-rules/"]')
            ]
            return {
                "range": _norm(cells[0]),
                "strength": _norm(cells[1]),
                "ap": _norm(cells[2]),
                "special_rules": special_rules,
            }
        except Exception:  # noqa: BLE001
            logger.warning("_extract_weapon_profile: unexpected error; returning defaults")
            return empty

    def _extract_spell_type(self, html: str) -> str | None:
        """Extract the spell type from the single ``div.spell`` block on a dedicated spell page.

        Looks for the ``Type`` stat row and returns the text of its ``<a href="/magic/...">``
        anchor (e.g. ``"Enchantment"``, ``"Magic Missile"``).  Returns ``None`` when the block
        is absent or the Type row has no magic-category link (e.g. bound spells).
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
            block = soup.select_one("div.spell")
            if block is None:
                return None
            for row in block.select("table tr"):
                cells = row.select("td")
                if len(cells) < 2:
                    continue
                if cells[0].get_text(strip=True) != "Type":
                    continue
                type_a = cells[1].select_one('a[href^="/magic/"]')
                return type_a.get_text(strip=True) or None if type_a else None
        except Exception:  # noqa: BLE001
            logger.warning("_extract_spell_type: unexpected error; returning None")
        return None

    def _richtext_entry_links_typed(self, node: dict | None) -> list[tuple[str, str]]:
        """Return ``(slug, contentType)`` pairs from entry-hyperlink nodes.

        Useful when the caller needs to branch on whether the linked entry is an
        ``armyListEntry`` (mount), ``rule`` (weapon/rule), etc.
        """
        if not isinstance(node, dict):
            return []
        results: list[tuple[str, str]] = []
        if node.get("nodeType") in ("entry-hyperlink", "embedded-entry-inline"):
            target = node.get("data", {}).get("target", {})
            slug = target.get("fields", {}).get("slug")
            ct = target.get("sys", {}).get("contentType", {}).get("sys", {}).get("id", "")
            if slug:
                results.append((slug, ct))
        for child in node.get("content", []):
            results.extend(self._richtext_entry_links_typed(child))
        return results
