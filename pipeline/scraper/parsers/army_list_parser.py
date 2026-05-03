"""
Parser for army-list composition pages (``/warhammer-armies/<army>-army-list``).

Extracts from each army's Grand Army Composition List:
- :CompositionList   — one per army, with slot caps.
- :CompositionSlot   — one per (army, slot_name) pair.
- SLOT_ALLOWS edges  — slot → unit, with optional {max_count, per_points} properties.
- ALLIED_WITH edges  — army → army, with alliance_type.
- :Upgrade nodes     — command_bsb upgrades for each eligible BSB character.
- HAS_UPGRADE edges  — character → bsb upgrade.

Data source: ``__NEXT_DATA__.props.pageProps.entry.fields.body`` (Contentful rich-text).
The body uses heading-3 sections: Characters, Core, Special, Rare, Mercenaries, Allies,
Battle Standard Bearer.
"""

from __future__ import annotations

import logging
import re

from pipeline.constants import EdgeType, NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)

# heading-3 text → canonical slot_name used in CompositionSlot nodes
_SLOT_NAME_MAP: dict[str, str] = {
    "characters": "Characters",
    "core": "Core",
    "special": "Special",
    "rare": "Rare",
    "mercenaries": "Mercenaries",
    "allies": "Allies",
}

_PCT_RE = re.compile(r"(up\s+to|at\s+least)\s+(\d+)\s*%", re.IGNORECASE)
_COST_RE = re.compile(r"\+(\d+)\s+point", re.IGNORECASE)
_PER_UNIT_RE = re.compile(r"0-(\d+)\s+[\w\s]*per\s+([\d,]+)\s+points?", re.IGNORECASE)
_ALLIANCE_TYPE_RE = re.compile(r"\(\s*(suspicious|trusted|uneasy)\s*\)", re.IGNORECASE)
_BSB_CHAR_RE = re.compile(
    r"A\s+single\s+([\w\s\-',()]+?)\s+in\s+your\s+army\s+may\s+be\s+upgraded", re.IGNORECASE
)
_UNLIMITED_BSB_RE = re.compile(
    r"magic\s+standard\s+with\s+no\s+points\s+limit"
    r"|no\s+points\s+limit"
    r"|unlimited\s+magic\s+standard",
    re.IGNORECASE,
)


class ArmyListParser(BaseParser):
    """Parse an army-list composition page."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("ArmyListParser: ISR fallback or missing data at %s", url)
            return result

        entry = pp.get("entry", {})
        if not entry:
            logger.warning("ArmyListParser: no entry in pageProps at %s", url)
            return result

        fields = entry.get("fields", {})
        slug: str = fields.get("slug") or self._slug(url)
        army_slug = self._army_slug_from_list_slug(slug)

        body = fields.get("body")
        if not body:
            logger.warning("ArmyListParser: no body field at %s", url)
            return result

        # Build the CompositionList node
        list_id = f"{army_slug}#composition-list"
        list_node: dict = {
            "node_type": NodeType.COMPOSITION_LIST,
            "id": list_id,
            "army_id": army_slug,
            "url": url,
        }
        result.nodes.append(list_node)
        result.edges.append(self._make_edge(army_slug, list_id, EdgeType.HAS_LIST))

        # Walk heading-3 sections
        sections = self._extract_heading3_sections(body)

        for section_name, section_nodes in sections.items():
            canonical = _SLOT_NAME_MAP.get(section_name.lower())

            if canonical in ("Characters", "Core", "Special", "Rare", "Mercenaries"):
                self._process_slot_section(
                    result, army_slug, list_id, canonical, section_nodes
                )
            elif section_name.lower() == "allies" or section_name.lower().endswith("allies"):
                self._process_allies_section(result, army_slug, section_nodes)
            elif section_name.lower() == "battle standard bearer":
                self._process_bsb_section(result, army_slug, section_nodes)
            # Other sections (e.g. "Magic Items" overrides) — ignored for now

        return result

    # ------------------------------------------------------------------
    # Slot section
    # ------------------------------------------------------------------

    def _process_slot_section(
        self,
        result: ParseResult,
        army_slug: str,
        list_id: str,
        slot_name: str,
        nodes: list[dict],
    ) -> None:
        """Emit a :CompositionSlot + SLOT_ALLOWS edges."""
        slot_id = f"{list_id}#{slot_name.lower()}"
        min_pct: int | None = None
        max_pct: int | None = None

        # First paragraph carries the % cap
        for node in nodes:
            if node.get("nodeType") == "paragraph":
                text = self._richtext_to_text(node)
                m = _PCT_RE.search(text)
                if m:
                    qualifier = m.group(1).lower()
                    pct = int(m.group(2))
                    if "least" in qualifier:
                        min_pct = pct
                    else:
                        max_pct = pct
                break  # only first paragraph

        slot_node: dict = {
            "node_type": NodeType.COMPOSITION_SLOT,
            "id": slot_id,
            "composition_list_id": list_id,
            "army_id": army_slug,
            "slot_name": slot_name,
            "min_pct": min_pct,
            "max_pct": max_pct,
        }
        result.nodes.append(slot_node)
        result.edges.append(self._make_edge(list_id, slot_id, EdgeType.HAS_SLOT))

        # Collect SLOT_ALLOWS edges from list items
        for node in nodes:
            if node.get("nodeType") in ("unordered-list", "ordered-list"):
                for item in node.get("content", []):
                    if item.get("nodeType") != "list-item":
                        continue
                    self._emit_slot_allows(result, slot_id, item)

    def _emit_slot_allows(self, result: ParseResult, slot_id: str, item: dict) -> None:
        """Emit SLOT_ALLOWS edges for all armyListEntry links in an item (recursive)."""
        item_text = self._richtext_to_text(item)
        # per-1000-pts constraint on this item
        max_count, per_points = self._parse_per_constraint(item_text)

        for slug, ct in self._richtext_entry_links_typed(item):
            if ct == "armyListEntry":
                props: dict = {}
                if max_count is not None:
                    props["max_count"] = max_count
                if per_points is not None:
                    props["per_points"] = per_points
                result.edges.append(self._make_edge(slot_id, slug, EdgeType.SLOT_ALLOWS, props))

    # ------------------------------------------------------------------
    # Allies section
    # ------------------------------------------------------------------

    def _process_allies_section(
        self,
        result: ParseResult,
        army_slug: str,
        nodes: list[dict],
    ) -> None:
        """Emit ALLIED_WITH edges by walking to innermost list-items."""
        for node in nodes:
            if node.get("nodeType") in ("unordered-list", "ordered-list"):
                for item in node.get("content", []):
                    if item.get("nodeType") != "list-item":
                        continue
                    for leaf in self._flatten_list_item_leaves(item):
                        self._emit_ally_edges(result, army_slug, leaf)

    def _flatten_list_item_leaves(self, item: dict) -> list[dict]:
        """Return leaf list-items (no nested list) from a potentially nested list-item."""
        nested: dict | None = None
        for child in item.get("content", []):
            if child.get("nodeType") in ("unordered-list", "ordered-list"):
                nested = child
                break
        if nested is None:
            return [item]
        leaves: list[dict] = []
        for child in nested.get("content", []):
            if child.get("nodeType") == "list-item":
                leaves.extend(self._flatten_list_item_leaves(child))
        return leaves if leaves else [item]

    def _emit_ally_edges(
        self, result: ParseResult, army_slug: str, item: dict
    ) -> None:
        """Emit one ALLIED_WITH edge per allied army found in a leaf list-item."""
        # Use only the paragraph text of this leaf (not recursive) to get alliance type
        para_text = ""
        for child in item.get("content", []):
            if child.get("nodeType") == "paragraph":
                para_text = self._richtext_to_text(child)
                break
        m_type = _ALLIANCE_TYPE_RE.search(para_text)
        alliance_type = m_type.group(1).lower() if m_type else "trusted"

        for slug, ct in self._richtext_entry_links_typed(item):
            ally_slug: str | None = None
            if ct == "association":
                ally_slug = slug
            elif ct == "rule" and slug.endswith("-army-list"):
                # e.g. "grand-cathay-army-list" → "grand-cathay"
                ally_slug = slug.removesuffix("-army-list")

            if ally_slug and ally_slug != army_slug:
                result.edges.append(
                    self._make_edge(
                        army_slug,
                        ally_slug,
                        EdgeType.ALLIED_WITH,
                        {"alliance_type": alliance_type},
                    )
                )

    # ------------------------------------------------------------------
    # BSB section
    # ------------------------------------------------------------------

    def _process_bsb_section(
        self,
        result: ParseResult,
        army_slug: str,
        nodes: list[dict],
    ) -> None:
        """Emit command_bsb :Upgrade nodes for each eligible character."""
        for node in nodes:
            if node.get("nodeType") != "paragraph":
                continue
            text = self._richtext_to_text(node)
            if not text.strip():
                continue

            # Cost: "+25 points"
            m_cost = _COST_RE.search(text)
            points_cost = int(m_cost.group(1)) if m_cost else None

            # Unlimited magic standard?
            unlimited = bool(_UNLIMITED_BSB_RE.search(text))

            # Character slug: prefer armyListEntry hyperlinks; fall back to text extraction.
            char_slugs: list[str] = [
                s for s, ct in self._richtext_entry_links_typed(node) if ct == "armyListEntry"
            ]
            if not char_slugs:
                m_char = _BSB_CHAR_RE.search(text)
                if m_char:
                    raw = m_char.group(1).strip()
                    # Handle "X, Y or Z" / "X (Qualifier)" — split on commas and "or"
                    raw_no_parens = re.sub(r"\([^)]*\)", "", raw).strip()
                    parts = re.split(r"\s*,\s*|\s+or\s+", raw_no_parens)
                    char_slugs = [self._name_to_slug(p.strip()) for p in parts if p.strip()]

            for char_slug in char_slugs:
                upgrade_id = f"{char_slug}#upgrade-bsb-{army_slug}"
                upgrade_node: dict = {
                    "node_type": NodeType.UPGRADE,
                    "id": upgrade_id,
                    "url": f"https://tow.whfb.app/unit/{char_slug}",
                    "name": "Battle Standard Bearer",
                    "description": text.strip(),
                    "upgrade_type": "command_bsb",
                    "points_cost": points_cost,
                    "cost_unit": "flat",
                    "points_budget": None,
                    "mutex_group": None,
                    "applies_to_profile": None,
                    "availability_constraint": None,
                    "replaces_weapon_id": None,
                    "bsb_unlimited_magic_standard": unlimited,
                    "order": 0,
                    "source_citation_book": army_slug,
                    "source_citation_page": None,
                }
                result.nodes.append(upgrade_node)
                result.edges.append(
                    self._make_edge(char_slug, upgrade_id, EdgeType.HAS_UPGRADE)
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _army_slug_from_list_slug(self, list_slug: str) -> str:
        """Convert '<army>-army-list' or '<army>-legacy-army-list' → army slug."""
        slug = list_slug
        # Strip known suffixes
        for suffix in ("-army-list", "-legacy"):
            if slug.endswith(suffix):
                slug = slug[: -len(suffix)]
        return slug

    def _extract_heading3_sections(self, body: dict) -> dict[str, list[dict]]:
        """Return {heading_text: [sibling_nodes_until_next_heading]} from a body rich-text."""
        sections: dict[str, list[dict]] = {}
        current_key: str | None = None
        for node in body.get("content", []):
            nt = node.get("nodeType", "")
            if nt in ("heading-2", "heading-3", "heading-4"):
                heading_text = self._richtext_to_text(node).strip()
                current_key = heading_text
                sections.setdefault(current_key, [])
            elif current_key is not None:
                sections[current_key].append(node)
        return sections

    def _parse_per_constraint(self, text: str) -> tuple[int | None, int | None]:
        """Parse '0-N X per Y,000 points' → (N, Y000)."""
        m = _PER_UNIT_RE.search(text)
        if not m:
            return None, None
        max_count = int(m.group(1))
        per_points_str = m.group(2).replace(",", "")
        per_points = int(per_points_str)
        return max_count, per_points
