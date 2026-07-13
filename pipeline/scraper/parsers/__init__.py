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
from pipeline.scraper.parsers.lore_parser import LoreParser
from pipeline.scraper.parsers.magic_item_parser import MagicItemParser
from pipeline.scraper.parsers.rule_parser import RuleParser
from pipeline.scraper.parsers.spell_parser import SpellParser
from pipeline.scraper.parsers.terrain_parser import TerrainParser
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
    "spell": LoreParser(),  # /the-lores-of-magic/{slug} — Lore node + membership edges
    "spell_page": SpellParser(),  # /spell/{slug} — dedicated Spell node
    "magic_item": MagicItemParser(),
    "weapon": WeaponParser(),
    "faq": FAQParser(),
    "errata": ErrataParser(),
    "terrain": TerrainParser(),
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
    "terrain": "terrains.json",
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
            url_path = entry["url"].split("tow.whfb.app")[-1].rstrip("/")
            if page_type == "magic_item" and not _has_embedded_magic_items(html):
                parser: BaseParser = _PARSERS["core_rule"]
            elif page_type == "core_rule" and entry["url"].rstrip("/").endswith("-army-list"):
                parser = _PARSERS["army_list"]
            elif page_type == "core_rule" and url_path.startswith("/spell/"):
                # Existing manifest labels /spell/{slug} pages as core_rule — route to SpellParser.
                parser = _PARSERS["spell_page"]
            elif page_type == "core_rule" and url_path.startswith("/magic-item/"):
                # Same bug class as /spell/ above (ADR-0006): manifest labels dedicated
                # /magic-item/{slug} pages as core_rule, creating a same-id CoreRule node
                # for every MagicItem. MagicItemParser handles both page shapes.
                parser = _PARSERS["magic_item"]
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
    # armour_add upgrades are excluded — they correctly point to armour Weapon nodes
    # but should stay typed as armour_add for category-filtered queries.
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
    logger.info(
        "Two-pass classifier: %d rule_add upgrades promoted to weapon_add", weapon_add_count
    )

    # --- Two-pass: renegade-lore BELONGS_TO_LORE edges ---
    # Renegade lore pages have no structured spell-slug list, so LoreParser emits zero
    # BELONGS_TO_LORE edges for them.  After all parsers run we have complete Spell nodes
    # (from dedicated pages) and Lore nodes (from lore pages).  We derive renegade membership
    # by matching each Spell name against the renegade Lore's text body.
    all_edges.extend(_derive_renegade_lore_membership(nodes_by_type, all_edges))

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

    # --- Derive CLARIFIES and AMENDS edges via name-matching ---
    # FAQ/Errata body rich-text has no CMS entry-hyperlinks, so the parsers emit 0
    # CLARIFIES/AMENDS edges from the Contentful link model.  This pass derives them
    # by matching known node names against FAQ question+answer text and Errata name fields.
    all_edges.extend(_derive_clarifies_amends(nodes_by_type))

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


# ---------------------------------------------------------------------------
# CLARIFIES / AMENDS edge derivation
# ---------------------------------------------------------------------------

# Node types whose names are matched against FAQ/Errata text.
_CLARIFIABLE_TYPES: tuple[str, ...] = (
    "special_rule",
    "core_rule",
    "unit",
    "spell",
    "weapon",
    "magic_item",
)

# Minimum character length for a name to be matched (short names like "Fear"
# or "Ld" produce too many false positives in running prose).
_MIN_MATCH_LEN: int = 5


def _derive_clarifies_amends(nodes_by_type: dict[str, list[dict]]) -> list[dict]:
    """Return CLARIFIES (FAQ→rule) and AMENDS (Errata→rule) edges derived from text.

    Strategy:
    - Errata: each node's ``name`` IS the rule being amended — direct slug lookup.
      Also scan ``corrected_text`` for embedded rule names.
    - FAQ: scan ``question`` + ``answer`` text for known rule names (case-sensitive,
      word-boundary, minimum length / multi-word filter to limit false positives).
    """
    # Build name → [node_id, ...] index (case-sensitive, original casing).
    # Short single-word names are excluded from the FAQ text-scan index to reduce
    # false positives, but kept in the id-lookup set used for Errata name matching.
    name_to_ids: dict[str, list[str]] = {}
    for node_type in _CLARIFIABLE_TYPES:
        for node in nodes_by_type.get(node_type, []):
            name: str = (node.get("name") or "").strip()
            nid: str = node.get("id", "")
            if not name or not nid:
                continue
            # Only index names that pass the length threshold for FAQ text scanning.
            # Single short words (< _MIN_MATCH_LEN chars) are too noisy.
            words = name.split()
            if len(name) >= _MIN_MATCH_LEN or len(words) >= 2:
                name_to_ids.setdefault(name, []).append(nid)

    # Build full id set for Errata slug-lookup (no length restriction needed).
    all_ids: set[str] = {
        node.get("id", "") for nodes in nodes_by_type.values() for node in nodes if node.get("id")
    }

    # Pre-compile regex patterns for FAQ scanning (whole-word, case-insensitive for
    # names that appear in prose; use re.escape for safety).
    # Build once and cache as (pattern, [ids]) tuples.
    _faq_patterns: list[tuple[re.Pattern[str], list[str]]] = []
    for name, ids in name_to_ids.items():
        try:
            pat = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
            _faq_patterns.append((pat, ids))
        except re.error:
            continue

    new_edges: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(src: str, dst: str, relation: str) -> None:
        key = (src, dst, relation)
        if key not in seen and dst in all_ids:
            seen.add(key)
            new_edges.append({"src": src, "dst": dst, "relation": relation, "properties": {}})

    def _name_to_slug_local(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    # --- AMENDS (Errata → rule) ---
    for errata in nodes_by_type.get("errata", []):
        errata_id = errata.get("id", "")
        if not errata_id:
            continue
        rule_name: str = (errata.get("name") or "").strip()
        if rule_name:
            slug = _name_to_slug_local(rule_name)
            _add(errata_id, slug, EdgeType.AMENDS)
        # Also scan corrected_text for embedded proper rule names
        corrected: str = errata.get("corrected_text") or ""
        for pat, ids in _faq_patterns:
            if pat.search(corrected):
                for rid in ids:
                    _add(errata_id, rid, EdgeType.AMENDS)

    # --- CLARIFIES (FAQ → rule) ---
    for faq in nodes_by_type.get("faq", []):
        faq_id = faq.get("id", "")
        if not faq_id:
            continue
        text = (faq.get("question") or "") + " " + (faq.get("answer") or "")
        if not text.strip():
            continue
        for pat, ids in _faq_patterns:
            if pat.search(text):
                for rid in ids:
                    _add(faq_id, rid, EdgeType.CLARIFIES)

    logger.info(
        "Text-based derivation: %d CLARIFIES + %d AMENDS edges",
        sum(1 for e in new_edges if e["relation"] == EdgeType.CLARIFIES),
        sum(1 for e in new_edges if e["relation"] == EdgeType.AMENDS),
    )
    return new_edges


# ---------------------------------------------------------------------------
# Renegade-lore BELONGS_TO_LORE derivation
# ---------------------------------------------------------------------------


def _derive_renegade_lore_membership(
    nodes_by_type: dict[str, list[dict]],
    existing_edges: list[dict],
) -> list[dict]:
    """Return ``BELONGS_TO_LORE`` edges for renegade lores via spell-name matching.

    Renegade lore pages have no embedded spell-slug list so ``LoreParser`` emits zero
    ``BELONGS_TO_LORE`` edges for them.  This pass derives membership by matching each
    Spell node's name (case-insensitive, whole-word) against the renegade Lore's text body.

    Only lores that have received **zero** structural ``BELONGS_TO_LORE`` edges (i.e.
    renegade lores) are considered, preventing standard-lore spells from picking up false
    cross-lore memberships.
    """
    # Lores that already have at least one BELONGS_TO_LORE edge are standard lores.
    lores_with_edges: set[str] = {
        e["dst"] for e in existing_edges if e.get("relation") == EdgeType.BELONGS_TO_LORE
    }

    renegade_lores = [
        n for n in nodes_by_type.get("lore", []) if n.get("id") and n["id"] not in lores_with_edges
    ]
    if not renegade_lores:
        return []

    spell_nodes = nodes_by_type.get("spell", [])

    new_edges: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for lore in renegade_lores:
        lore_id = lore["id"]
        lore_text: str = lore.get("text") or ""
        if not lore_text:
            continue

        for spell in spell_nodes:
            spell_id = spell.get("id", "")
            if not spell_id:
                continue
            spell_name: str = spell.get("name") or ""
            if not spell_name:
                continue
            if re.search(r"\b" + re.escape(spell_name) + r"\b", lore_text, re.IGNORECASE):
                key = (spell_id, lore_id)
                if key not in seen:
                    seen.add(key)
                    new_edges.append(
                        {
                            "src": spell_id,
                            "dst": lore_id,
                            "relation": EdgeType.BELONGS_TO_LORE,
                            "properties": {},
                        }
                    )

    logger.info(
        "Renegade-lore two-pass: %d BELONGS_TO_LORE edges derived for %d renegade lore(s)",
        len(new_edges),
        len(renegade_lores),
    )
    return new_edges
