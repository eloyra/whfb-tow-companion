"""
Per-label embedding text builders.

Each builder queries the graph for a batch of node IDs and returns the
corresponding dense text strings used to generate embeddings.  Text is
built from graph context (neighbors pulled via Cypher), not from raw JSON,
so it captures rules, weapons, profiles, and army associations that make
semantic queries like "fast cavalry with high attacks" work.

Public API:
    build_for_label(driver, label, ids) -> list[str]
        Returns one text string per id, in the same order as ids.
        Empty string means the node has no embeddable text; the caller skips it.
"""

from __future__ import annotations

import logging

import neo4j

logger = logging.getLogger(__name__)


def build_for_label(driver: neo4j.Driver, label: str, ids: list[str]) -> list[str]:
    """Return embedding texts for *ids* of the given *label*."""
    builder = _BUILDERS.get(label)
    if builder is None:
        logger.warning("No embedding text builder for label %s — using name only", label)
        return _build_name_only(driver, label, ids)
    return builder(driver, ids)


# ---------------------------------------------------------------------------
# Individual label builders
# ---------------------------------------------------------------------------


def _build_special_rule(driver: neo4j.Driver, ids: list[str]) -> list[str]:
    query = """
        UNWIND $ids AS nid
        MATCH (n:SpecialRule {id: nid})
        RETURN nid, n.name AS name, n.text AS text
    """
    return _format_name_text(driver, query, ids)


def _build_core_rule(driver: neo4j.Driver, ids: list[str]) -> list[str]:
    query = """
        UNWIND $ids AS nid
        MATCH (n:CoreRule {id: nid})
        RETURN nid, n.name AS name, n.text AS text
    """
    return _format_name_text(driver, query, ids)


def _build_document(driver: neo4j.Driver, ids: list[str]) -> list[str]:
    query = """
        UNWIND $ids AS nid
        MATCH (n:Document {id: nid})
        RETURN nid, n.name AS name, n.text AS text
    """
    return _format_name_text(driver, query, ids)


def _build_troop_type(driver: neo4j.Driver, ids: list[str]) -> list[str]:
    query = """
        UNWIND $ids AS nid
        MATCH (n:TroopType {id: nid})
        RETURN nid,
               n.name AS name,
               n.category AS category,
               n.min_models_for_rank_bonus AS min_rank,
               n.max_rank_bonus AS max_rank,
               n.unit_strength_per_model AS strength,
               n.text AS text
    """
    rows = _fetch(driver, query, ids)
    result: dict[str, str] = {}
    for rec in rows:
        nid = rec["nid"]
        parts = [rec["name"] or ""]
        if rec["category"]:
            parts.append(rec["category"])
        if rec["min_rank"] is not None:
            parts.append(f"Rank bonus min {rec['min_rank']} / max +{rec['max_rank']}")
        if rec["strength"]:
            parts.append(f"Unit strength {rec['strength']}")
        if rec["text"]:
            parts.append(rec["text"])
        result[nid] = ". ".join(p for p in parts if p)
    return [result.get(nid, "") for nid in ids]


def _build_spell(driver: neo4j.Driver, ids: list[str]) -> list[str]:
    query = """
        UNWIND $ids AS nid
        MATCH (n:Spell {id: nid})
        OPTIONAL MATCH (n)-[:BELONGS_TO_LORE]->(l:Lore)
        RETURN nid, n.name AS name, n.text AS text, l.name AS lore_name
    """
    rows = _fetch(driver, query, ids)
    result: dict[str, str] = {}
    for rec in rows:
        nid = rec["nid"]
        parts = [rec["name"] or ""]
        if rec["lore_name"]:
            parts.append(f"Lore of {rec['lore_name']}")
        if rec["text"]:
            parts.append(rec["text"])
        result[nid] = ". ".join(p for p in parts if p)
    return [result.get(nid, "") for nid in ids]


def _build_magic_item(driver: neo4j.Driver, ids: list[str]) -> list[str]:
    query = """
        UNWIND $ids AS nid
        MATCH (n:MagicItem {id: nid})
        RETURN nid, n.name AS name, n.item_type AS item_type,
               n.points_cost AS cost, n.text AS text
    """
    rows = _fetch(driver, query, ids)
    result: dict[str, str] = {}
    for rec in rows:
        nid = rec["nid"]
        parts = [rec["name"] or ""]
        if rec["item_type"]:
            parts.append(rec["item_type"].replace("_", " "))
        if rec["cost"] is not None:
            parts.append(f"{rec['cost']} pts")
        if rec["text"]:
            parts.append(rec["text"])
        result[nid] = ". ".join(p for p in parts if p)
    return [result.get(nid, "") for nid in ids]


def _build_lore(driver: neo4j.Driver, ids: list[str]) -> list[str]:
    query = """
        UNWIND $ids AS nid
        MATCH (n:Lore {id: nid})
        OPTIONAL MATCH (s:Spell)-[:BELONGS_TO_LORE]->(n)
        WITH nid, n.name AS name, n.text AS text, collect(s.name) AS spell_names
        RETURN nid, name, text, spell_names
    """
    rows = _fetch(driver, query, ids)
    result: dict[str, str] = {}
    for rec in rows:
        nid = rec["nid"]
        parts = [rec["name"] or ""]
        if rec["text"]:
            parts.append(rec["text"])
        if rec["spell_names"]:
            parts.append("Spells: " + ", ".join(sorted(rec["spell_names"])))
        result[nid] = ". ".join(p for p in parts if p)
    return [result.get(nid, "") for nid in ids]


def _build_faq(driver: neo4j.Driver, ids: list[str]) -> list[str]:
    query = """
        UNWIND $ids AS nid
        MATCH (n:FAQ {id: nid})
        RETURN nid, n.question AS question, n.answer AS answer
    """
    rows = _fetch(driver, query, ids)
    result: dict[str, str] = {}
    for rec in rows:
        nid = rec["nid"]
        parts = []
        if rec["question"]:
            parts.append(rec["question"])
        if rec["answer"]:
            parts.append(rec["answer"])
        result[nid] = " ".join(parts)
    return [result.get(nid, "") for nid in ids]


def _build_errata(driver: neo4j.Driver, ids: list[str]) -> list[str]:
    query = """
        UNWIND $ids AS nid
        MATCH (n:Errata {id: nid})
        RETURN nid, n.original_text AS original, n.corrected_text AS corrected, n.name AS name
    """
    rows = _fetch(driver, query, ids)
    result: dict[str, str] = {}
    for rec in rows:
        nid = rec["nid"]
        parts = []
        if rec["name"]:
            parts.append(rec["name"])
        if rec["original"]:
            parts.append(f"Original: {rec['original']}")
        if rec["corrected"]:
            parts.append(f"Corrected: {rec['corrected']}")
        result[nid] = ". ".join(parts)
    return [result.get(nid, "") for nid in ids]


def _build_weapon(driver: neo4j.Driver, ids: list[str]) -> list[str]:
    query = """
        UNWIND $ids AS nid
        MATCH (n:Weapon {id: nid})
        RETURN nid, n.name AS name, n.weapon_class AS weapon_class,
               n.range AS range, n.strength AS strength, n.ap AS ap,
               n.shots AS shots, n.special_rules AS special_rules,
               n.armour_value AS armour_value, n.text AS text
    """
    rows = _fetch(driver, query, ids)
    result: dict[str, str] = {}
    for rec in rows:
        nid = rec["nid"]
        parts = [rec["name"] or ""]
        if rec["weapon_class"]:
            parts.append(rec["weapon_class"].replace("_", " "))
        stats = []
        if rec["range"] is not None:
            stats.append(f"Range {rec['range']}")
        if rec["strength"] is not None:
            stats.append(f"Str {rec['strength']}")
        if rec["ap"] is not None:
            stats.append(f"AP {rec['ap']}")
        if rec["shots"] is not None:
            stats.append(f"Shots {rec['shots']}")
        if rec["armour_value"] is not None:
            stats.append(f"AV {rec['armour_value']}")
        if stats:
            parts.append(" ".join(stats))
        if rec["special_rules"]:
            rules = rec["special_rules"]
            if isinstance(rules, list):
                parts.append("Special rules: " + ", ".join(str(r) for r in rules))
        if rec["text"]:
            parts.append(rec["text"])
        result[nid] = ". ".join(p for p in parts if p)
    return [result.get(nid, "") for nid in ids]


def _build_unit(driver: neo4j.Driver, ids: list[str]) -> list[str]:
    # Fetch unit base fields
    unit_query = """
        UNWIND $ids AS nid
        MATCH (n:Unit {id: nid})
        OPTIONAL MATCH (n)-[:BELONGS_TO]->(a:Army)
        OPTIONAL MATCH (n)-[:HAS_TYPE]->(tt:TroopType)
        RETURN nid,
               n.name AS name,
               n.army_category AS army_category,
               n.cost_points_per_model AS cost,
               n.unit_size_min AS size_min,
               n.unit_size_max AS size_max,
               n.base_width_mm AS bw,
               n.base_depth_mm AS bd,
               n.av_intrinsic AS av,
               collect(DISTINCT a.name) AS armies,
               collect(DISTINCT tt.name) AS troop_types
    """
    # Fetch profiles per unit
    profile_query = """
        UNWIND $ids AS nid
        MATCH (u:Unit {id: nid})-[:HAS_PROFILE]->(p:Profile)
        RETURN nid, p.name AS pname,
               p.M AS M, p.WS AS WS, p.BS AS BS, p.S AS S, p.T AS T,
               p.W AS W, p.I AS I, p.A AS A, p.Ld AS Ld, p.order AS ord
        ORDER BY nid, p.order
    """
    # Fetch rules, weapons, and upgrades
    edge_query = """
        UNWIND $ids AS nid
        MATCH (u:Unit {id: nid})
        OPTIONAL MATCH (u)-[:HAS_RULE|HAS_OPTIONAL_RULE]->(r:SpecialRule)
        OPTIONAL MATCH (u)-[:HAS_WEAPON]->(w:Weapon)
        OPTIONAL MATCH (u)-[:HAS_UPGRADE]->(up:Upgrade)
        RETURN nid,
               collect(DISTINCT r.name) AS rules,
               collect(DISTINCT w.name) AS weapons,
               collect(DISTINCT up.name) AS upgrades
    """

    unit_rows = _fetch(driver, unit_query, ids)
    profile_rows = _fetch(driver, profile_query, ids)
    edge_rows = _fetch(driver, edge_query, ids)

    # Index by nid
    units: dict[str, dict] = {rec["nid"]: rec for rec in unit_rows}
    profiles_by_unit: dict[str, list[dict]] = {}
    for rec in profile_rows:
        profiles_by_unit.setdefault(rec["nid"], []).append(rec)
    edges_by_unit: dict[str, dict] = {rec["nid"]: rec for rec in edge_rows}

    result: dict[str, str] = {}
    for nid in ids:
        u = units.get(nid)
        if not u:
            result[nid] = ""
            continue

        parts = [u["name"] or ""]

        armies = [a for a in (u["armies"] or []) if a]
        if armies:
            parts.append(", ".join(armies))

        troop_types = [t for t in (u["troop_types"] or []) if t]
        if troop_types:
            parts.append(", ".join(troop_types))

        if u["army_category"]:
            parts.append(u["army_category"])

        cost = u["cost"]
        if cost is not None:
            parts.append(f"{cost} pts/model")

        size_min, size_max = u["size_min"], u["size_max"]
        if size_min is not None:
            size_str = f"{size_min}-{size_max}" if size_max else f"{size_min}+"
            parts.append(f"Unit size {size_str}")

        bw, bd = u["bw"], u["bd"]
        if bw and bd:
            parts.append(f"Base {bw}x{bd}mm")

        if u["av"]:
            parts.append(f"Armour save {u['av']}")

        # Profiles
        profs = profiles_by_unit.get(nid, [])
        if profs:
            prof_strs = []
            for p in sorted(profs, key=lambda x: x.get("ord", 0)):
                stats = []
                for stat in ("M", "WS", "BS", "S", "T", "W", "I", "A", "Ld"):
                    val = p.get(stat)
                    if val is not None:
                        stats.append(f"{stat}{val}")
                prof_strs.append(f"{p['pname']}: {' '.join(stats)}" if stats else p["pname"])
            parts.append("Profiles — " + "; ".join(prof_strs))

        # Rules, weapons, and upgrades
        ev = edges_by_unit.get(nid, {})
        rules = [r for r in (ev.get("rules") or []) if r]
        weapons = [w for w in (ev.get("weapons") or []) if w]
        upgrade_names = [u for u in (ev.get("upgrades") or []) if u]
        if rules:
            parts.append("Rules: " + ", ".join(sorted(rules)))
        if weapons:
            parts.append("Weapons: " + ", ".join(sorted(weapons)))
        if upgrade_names:
            parts.append("Upgrades: " + ", ".join(sorted(upgrade_names)))

        result[nid] = ". ".join(p for p in parts if p)

    return [result.get(nid, "") for nid in ids]


def _build_army(driver: neo4j.Driver, ids: list[str]) -> list[str]:
    query = """
        UNWIND $ids AS nid
        MATCH (n:Army {id: nid})
        RETURN nid, n.name AS name
    """
    rows = _fetch(driver, query, ids)
    result: dict[str, str] = {rec["nid"]: rec["name"] or "" for rec in rows}
    return [result.get(nid, "") for nid in ids]


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_BUILDERS = {
    "SpecialRule": _build_special_rule,
    "CoreRule": _build_core_rule,
    "Document": _build_document,
    "TroopType": _build_troop_type,
    "Spell": _build_spell,
    "MagicItem": _build_magic_item,
    "Lore": _build_lore,
    "FAQ": _build_faq,
    "Errata": _build_errata,
    "Weapon": _build_weapon,
    "Unit": _build_unit,
    "Army": _build_army,
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _fetch(driver: neo4j.Driver, query: str, ids: list[str]) -> list[dict]:
    with driver.session() as session:
        result = session.run(query, ids=ids)
        return [dict(rec) for rec in result]


def _format_name_text(driver: neo4j.Driver, query: str, ids: list[str]) -> list[str]:
    """Generic builder: concatenate name + text."""
    rows = _fetch(driver, query, ids)
    result: dict[str, str] = {}
    for rec in rows:
        nid = rec["nid"]
        parts = []
        if rec.get("name"):
            parts.append(rec["name"])
        if rec.get("text"):
            parts.append(rec["text"])
        result[nid] = ". ".join(parts)
    return [result.get(nid, "") for nid in ids]


def _build_name_only(driver: neo4j.Driver, label: str, ids: list[str]) -> list[str]:
    query = f"UNWIND $ids AS nid MATCH (n:{label} {{id: nid}}) RETURN nid, n.name AS name"
    rows = _fetch(driver, query, ids)
    result: dict[str, str] = {rec["nid"]: rec.get("name") or "" for rec in rows}
    return [result.get(nid, "") for nid in ids]
