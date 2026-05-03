"""
Parser registry and pipeline coordinator for the parse stage.

``run_all_parsers()`` is the entry point called by ``pipeline/run_pipeline.py``.
It reads ``data/raw/manifest.json``, dispatches each page to the appropriate
parser, aggregates all nodes and edges, and writes one JSON file per node type
to ``data/parsed/``.

Output files:
    data/parsed/armies.json
    data/parsed/units.json
    data/parsed/profiles.json     ← stat-profile sub-nodes extracted from Unit pages
    data/parsed/special_rules.json
    data/parsed/core_rules.json
    data/parsed/documents.json
    data/parsed/troop_types.json
    data/parsed/weapons.json
    data/parsed/spells.json
    data/parsed/magic_items.json
    data/parsed/faqs.json
    data/parsed/errata.json
    data/parsed/edges.json        ← includes HAS_PROFILE edges

All node records are written in graph-safe flat form: no nested maps or
lists-of-maps.  ``source_citation`` is split into ``source_citation_book`` /
``source_citation_page`` scalars; ``base_size_mm`` into ``base_width_mm`` /
``base_depth_mm``; ``unit_size`` into ``unit_size_min`` / ``unit_size_max``.
Stat profiles are emitted as separate ``Profile`` records (see ADR-0004 amendment).
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from tqdm import tqdm

from pipeline.constants import EdgeType
from pipeline.scraper.parsers.army_list_parser import ArmyListParser
from pipeline.scraper.parsers.army_parser import ArmyParser
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult
from pipeline.scraper.parsers.core_rule_parser import CoreRuleParser
from pipeline.scraper.parsers.errata_parser import ErrataParser
from pipeline.scraper.parsers.faq_parser import FAQParser
from pipeline.scraper.parsers.magic_item_parser import MagicItemParser
from pipeline.scraper.parsers.rule_parser import RuleParser
from pipeline.scraper.parsers.spell_parser import SpellParser
from pipeline.scraper.parsers.unit_parser import UnitParser
from pipeline.scraper.parsers.weapon_parser import WeaponParser

logger = logging.getLogger(__name__)

_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Parser registry
# Maps page_type (from manifest) → parser instance.
# Page types not in this registry are silently skipped.
# ---------------------------------------------------------------------------

_PARSERS: dict[str, BaseParser] = {
    "army": ArmyParser(),
    "unit": UnitParser(),
    "special_rule": RuleParser(),
    "troop_type": RuleParser(),  # RuleParser handles both special_rule + troop_type
    "core_rule": CoreRuleParser(),
    "army_list": ArmyListParser(),
    "spell": SpellParser(),
    "magic_item": MagicItemParser(),
    "weapon": WeaponParser(),
    "faq": FAQParser(),
    "errata": ErrataParser(),
}

# ---------------------------------------------------------------------------
# node_type → output filename mapping
# ---------------------------------------------------------------------------

_NODE_TYPE_TO_FILE: dict[str, str] = {
    "army": "armies.json",
    "unit": "units.json",
    "profile": "profiles.json",
    "lore": "lores.json",
    "special_rule": "special_rules.json",
    "core_rule": "core_rules.json",
    "document": "documents.json",
    "troop_type": "troop_types.json",
    "weapon": "weapons.json",
    "spell": "spells.json",
    "magic_item": "magic_items.json",
    "faq": "faqs.json",
    "errata": "errata.json",
    "upgrade": "upgrades.json",
    "composition_list": "composition_lists.json",
    "composition_slot": "composition_slots.json",
}

_RAW_DIR = Path("data/raw")
_PARSED_DIR = Path("data/parsed")


# ---------------------------------------------------------------------------
# Content-aware routing helpers
# ---------------------------------------------------------------------------


def _body_has_embedded_magic_items(node: dict) -> bool:
    """Return True if *node* or any descendant is an embedded-entry-block with magicItem data."""
    if not isinstance(node, dict):
        return False
    if node.get("nodeType") == "embedded-entry-block" and "magicItem" in node.get("data", {}):
        return True
    return any(_body_has_embedded_magic_items(child) for child in node.get("content", []))


def _has_embedded_magic_items(html: str) -> bool:
    """Return True if the page body contains at least one embedded magicItem block."""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return False
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return False
    body = (
        data.get("props", {})
        .get("pageProps", {})
        .get("entry", {})
        .get("fields", {})
        .get("body", {})
    )
    return _body_has_embedded_magic_items(body)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_all_parsers() -> None:
    """Read the crawl manifest and parse every page to structured JSON.

    Reads:  data/raw/manifest.json
    Writes: data/parsed/{node_type}.json for each node type
            data/parsed/edges.json
    """
    manifest_path = _RAW_DIR / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found at {manifest_path}. Run 'make scrape' first.")

    with manifest_path.open(encoding="utf-8") as fh:
        manifest: list[dict] = json.load(fh)

    logger.info("Parsing %d pages from manifest", len(manifest))

    nodes_by_type: dict[str, list[dict]] = defaultdict(list)
    all_edges: list[dict] = []
    skipped = 0

    for entry in tqdm(manifest, desc="Parsing pages", unit="page"):
        page_type: str = entry.get("page_type", "")
        if page_type not in _PARSERS:
            skipped += 1
            continue

        html_path = Path(entry["html_path"])
        if not html_path.exists():
            logger.warning("HTML file not found: %s", html_path)
            skipped += 1
            continue

        try:
            html = html_path.read_text(encoding="utf-8")

            # magic_item pages in the /magic-items/ section are a mix of actual item
            # list pages (embedded-entry-block with magicItem data) and rules/intro pages
            # (plain rich text with no item blocks).  Route the latter to CoreRuleParser
            # because the URL alone cannot distinguish them.
            if page_type == "magic_item" and not _has_embedded_magic_items(html):
                parser: BaseParser = _PARSERS["core_rule"]
            elif page_type == "core_rule" and entry["url"].rstrip("/").endswith("-army-list"):
                parser = _PARSERS["army_list"]
            else:
                parser = _PARSERS[page_type]

            result: ParseResult = parser.parse(
                html=html,
                url=entry["url"],
                fetched_at=entry.get("fetched_at", ""),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Parser error for %s: %s", entry["url"], exc, exc_info=True)
            skipped += 1
            continue

        for node in result.nodes:
            node_type = node.pop("node_type", None)
            if node_type:
                nodes_by_type[node_type].append(node)

        all_edges.extend(result.edges)

    # --- Two-pass classifier: relabel provisional UNLOCKS_RULE edges ---
    # Weapons and magic items are tagged as content-type "rule" in Contentful,
    # so _options.py emits UNLOCKS_RULE for all rule-type links.  Now that all
    # parsers have run we can build lookup sets and relabel correctly.
    _weapon_slugs: set[str] = {n["id"] for n in nodes_by_type.get("weapon", []) if "id" in n}
    _item_slugs: set[str] = {n["id"] for n in nodes_by_type.get("magic_item", []) if "id" in n}
    for edge in all_edges:
        if edge.get("relation") == EdgeType.UNLOCKS_RULE:
            dst = edge.get("dst", "")
            if dst in _weapon_slugs:
                edge["relation"] = EdgeType.UNLOCKS_WEAPON
            elif dst in _item_slugs:
                edge["relation"] = EdgeType.UNLOCKS_ITEM
            # else stays UNLOCKS_RULE
    unlocks_relabeled = sum(
        1
        for e in all_edges
        if e.get("relation") in (EdgeType.UNLOCKS_WEAPON, EdgeType.UNLOCKS_ITEM)
    )
    logger.info("Two-pass classifier: %d UNLOCKS_RULE edges relabeled", unlocks_relabeled)

    # Refine rule_add upgrade_type: promote to weapon_add when the upgrade
    # has at least one UNLOCKS_WEAPON or UNLOCKS_MOUNT edge.
    _upgrades_with_weapon_edge: set[str] = {
        e["src"]
        for e in all_edges
        if e.get("relation") in (EdgeType.UNLOCKS_WEAPON, EdgeType.UNLOCKS_MOUNT)
    }
    weapon_add_count = 0
    for node in nodes_by_type.get("upgrade", []):
        if node.get("upgrade_type") == "rule_add" and node.get("id") in _upgrades_with_weapon_edge:
            node["upgrade_type"] = "weapon_add"
            weapon_add_count += 1
    logger.info("Two-pass classifier: %d rule_add upgrades promoted to weapon_add", weapon_add_count)

    # --- Deduplicate nodes by (node_type, id) ---
    # Some pages (e.g. /faq contains all entries; /faq/<section> repeats a subset;
    # some spells/magic-items appear in multiple embedded pages).  Last occurrence
    # wins — section-specific pages come after the index page and carry richer context.
    total_before_dedup = sum(len(v) for v in nodes_by_type.values())
    deduped_by_type: dict[str, list[dict]] = {}
    for node_type, nodes in nodes_by_type.items():
        seen: dict[str, dict] = {}
        for node in nodes:
            nid = node.get("id")
            if nid:
                seen[nid] = node  # last wins
            else:
                seen[id(node)] = node  # no id — keep as-is
        deduped_by_type[node_type] = list(seen.values())
    total_after_dedup = sum(len(v) for v in deduped_by_type.values())
    if total_before_dedup != total_after_dedup:
        logger.info(
            "Deduplicated %d duplicate nodes → %d unique",
            total_before_dedup - total_after_dedup,
            total_after_dedup,
        )
    nodes_by_type = deduped_by_type

    # --- Filter dangling edges ---
    # Remove edges whose dst has no corresponding node to keep the graph valid.
    known_ids: set[str] = {
        node["id"] for nodes in nodes_by_type.values() for node in nodes if "id" in node
    }
    filtered_edges = [e for e in all_edges if e.get("dst") in known_ids]
    dropped = len(all_edges) - len(filtered_edges)
    if dropped:
        logger.info("Dropped %d edges with no matching dst node", dropped)

    # --- Deduplicate edges by (src, dst, relation) ---
    seen_edges: dict[tuple, dict] = {}
    for e in filtered_edges:
        key = (e.get("src"), e.get("dst"), e.get("relation"))
        if key not in seen_edges:
            seen_edges[key] = e
    deduped_edges = list(seen_edges.values())
    if len(deduped_edges) != len(filtered_edges):
        logger.info(
            "Deduplicated %d duplicate edges → %d unique",
            len(filtered_edges) - len(deduped_edges),
            len(deduped_edges),
        )
    filtered_edges = deduped_edges

    # --- Write output files ---
    _PARSED_DIR.mkdir(parents=True, exist_ok=True)

    for node_type, nodes in nodes_by_type.items():
        filename = _NODE_TYPE_TO_FILE.get(node_type, f"{node_type}.json")
        out_path = _PARSED_DIR / filename
        _write_json(out_path, nodes)
        logger.info("Written %d %s nodes → %s", len(nodes), node_type, out_path)

    edges_path = _PARSED_DIR / "edges.json"
    _write_json(edges_path, filtered_edges)
    logger.info("Written %d edges → %s", len(filtered_edges), edges_path)

    total_nodes = sum(len(v) for v in nodes_by_type.values())
    logger.info(
        "Parse stage complete: %d nodes, %d edges, %d pages skipped",
        total_nodes,
        len(all_edges),
        skipped,
    )


def _write_json(path: Path, data: list) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
