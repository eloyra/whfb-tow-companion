"""
Post-load integrity validator for the Neo4j knowledge graph.

``run_all(driver, parsed_dir)`` runs every check and writes a summary to
``data/graph/load_report.json``.  Non-zero drops are warnings unless a sanity
threshold is exceeded (>5% of a relation type missing → RuntimeError), with the
deliberate exception of PART_OF_SECTION whose drops are expected and documented.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import neo4j

logger = logging.getLogger(__name__)

# PART_OF_SECTION edges point to URL-prefix slugs never scraped as nodes.
# ~1 500 drops are expected — informational, not errors (see ADR-0004 amendment).
_EXPECTED_DROP_RELATIONS: frozenset[str] = frozenset({"PART_OF_SECTION"})

# Flag as error if more than this fraction of a relation type is missing.
_DROP_THRESHOLD = 0.05

_FILE_TO_LABEL: dict[str, str] = {
    "armies.json": "Army",
    "units.json": "Unit",
    "profiles.json": "Profile",
    "special_rules.json": "SpecialRule",
    "core_rules.json": "CoreRule",
    "documents.json": "Document",
    "troop_types.json": "TroopType",
    "lores.json": "Lore",
    "spells.json": "Spell",
    "weapons.json": "Weapon",
    "magic_items.json": "MagicItem",
    "faqs.json": "FAQ",
    "errata.json": "Errata",
    "upgrades.json": "Upgrade",
    "composition_lists.json": "CompositionList",
    "composition_slots.json": "CompositionSlot",
    "terrains.json": "Terrain",
}

_REPORT_DIR = Path("data/graph")


def run_all(driver: neo4j.Driver, parsed_dir: Path = Path("data/parsed")) -> dict:
    """Run all validation checks, write load_report.json, return the summary.

    Raises RuntimeError if unexpected drop rate exceeds the sanity threshold.
    """
    start = time.time()
    report: dict = {"checks": {}, "warnings": [], "threshold_errors": []}

    node_counts = _check_node_counts(driver, parsed_dir, report)
    edge_counts, edge_drops, threshold_errors = _check_edge_counts(driver, parsed_dir, report)
    _check_orphan_detail(driver, parsed_dir, report)
    _check_dangling_troop_types(driver, report)
    _check_upgrade_rule_add_ratio(driver, report)
    _check_dangling_applies_to_profile(driver, report)
    _check_armies_without_can_take_item(driver, report)
    _check_items_without_army_id_unreachable(driver, report)
    _check_faq_errata_coverage(driver, report)
    _check_intrinsic_rule_edges(driver, report)

    report["duration_seconds"] = round(time.time() - start, 2)
    report["node_counts"] = node_counts
    report["edge_counts"] = edge_counts
    report["edge_drops"] = edge_drops
    report["threshold_errors"] = threshold_errors

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = _REPORT_DIR / "load_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Load report → %s (%.1fs)", report_path, report["duration_seconds"])

    if threshold_errors:
        raise RuntimeError(
            f"Graph validation failed — {len(threshold_errors)} relation(s) exceeded "
            f"the {_DROP_THRESHOLD:.0%} drop threshold: {threshold_errors}"
        )

    return report


def _check_node_counts(driver: neo4j.Driver, parsed_dir: Path, report: dict) -> dict[str, dict]:
    with driver.session() as session:
        result = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c ORDER BY c DESC"
        )
        graph_counts: dict[str, int] = {rec["label"]: rec["c"] for rec in result}

    counts: dict[str, dict] = {}
    for filename, label in _FILE_TO_LABEL.items():
        json_path = parsed_dir / filename
        expected = (
            len(json.loads(json_path.read_text(encoding="utf-8"))) if json_path.exists() else 0
        )
        actual = graph_counts.get(label, 0)
        delta = actual - expected
        counts[label] = {"expected": expected, "actual": actual, "delta": delta}
        if delta != 0:
            msg = f"{label}: expected {expected}, got {actual} (delta {delta:+d})"
            report["warnings"].append(msg)
            logger.warning(msg)
        else:
            logger.info("%s: %d nodes OK", label, actual)

    return counts


def _check_edge_counts(
    driver: neo4j.Driver,
    parsed_dir: Path,
    report: dict,
) -> tuple[dict[str, int], dict[str, int], list[str]]:
    edges_path = parsed_dir / "edges.json"
    all_edges: list[dict] = (
        json.loads(edges_path.read_text(encoding="utf-8")) if edges_path.exists() else []
    )

    expected_by_rel: dict[str, int] = {}
    for e in all_edges:
        rel = e["relation"]
        expected_by_rel[rel] = expected_by_rel.get(rel, 0) + 1

    with driver.session() as session:
        result = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS c ORDER BY c DESC"
        )
        graph_rel_counts: dict[str, int] = {rec["rel"]: rec["c"] for rec in result}

    edge_counts: dict[str, int] = {}
    edge_drops: dict[str, int] = {}
    threshold_errors: list[str] = []

    for relation, expected in expected_by_rel.items():
        actual = graph_rel_counts.get(relation, 0)
        edge_counts[relation] = actual
        dropped = expected - actual
        if dropped <= 0:
            logger.info("%s: %d edges OK", relation, actual)
            continue

        edge_drops[relation] = dropped
        rate = dropped / expected
        is_expected = relation in _EXPECTED_DROP_RELATIONS

        if is_expected:
            logger.info(
                "%s: %d drops (expected — endpoint slugs not scraped as nodes)", relation, dropped
            )
        elif rate > _DROP_THRESHOLD:
            msg = (
                f"{relation}: {dropped}/{expected} dropped ({rate:.1%})"
                f" — exceeds {_DROP_THRESHOLD:.0%} threshold"
            )
            threshold_errors.append(msg)
            report["warnings"].append(msg)
            logger.error(msg)
        else:
            msg = f"{relation}: {dropped}/{expected} dropped ({rate:.1%})"
            report["warnings"].append(msg)
            logger.warning(msg)

    return edge_counts, edge_drops, threshold_errors


def _check_orphan_detail(driver: neo4j.Driver, parsed_dir: Path, report: dict) -> None:
    edges_path = parsed_dir / "edges.json"
    if not edges_path.exists():
        return

    all_edges: list[dict] = json.loads(edges_path.read_text(encoding="utf-8"))

    with driver.session() as session:
        result = session.run("MATCH (n) RETURN n.id AS nid")
        known: set[str] = {rec["nid"] for rec in result if rec["nid"]}

    missing_src: list[dict] = []
    missing_dst: list[dict] = []
    for e in all_edges:
        src, dst, rel = e.get("src"), e.get("dst"), e.get("relation")
        if src not in known:
            missing_src.append({"src": src, "dst": dst, "relation": rel})
        elif dst not in known:
            missing_dst.append({"src": src, "dst": dst, "relation": rel})

    report["checks"]["orphan_missing_src_count"] = len(missing_src)
    report["checks"]["orphan_missing_dst_count"] = len(missing_dst)
    report["checks"]["orphan_missing_dst_sample"] = missing_dst[:20]

    if missing_src:
        logger.warning("Edges with missing src node: %d", len(missing_src))
    logger.info("Edges with missing dst node: %d", len(missing_dst))


def _check_upgrade_rule_add_ratio(driver: neo4j.Driver, report: dict) -> None:
    """Warn if rule_add upgrades exceed 30% — likely a missed classifier pattern.

    weapon_add is excluded (those are correctly classified weapons promoted from rule_add
    during the coordinator two-pass, not missed patterns).
    """
    with driver.session() as session:
        total_rec = session.run("MATCH (u:Upgrade) RETURN count(u) AS c").single()
        ra_rec = session.run(
            "MATCH (u:Upgrade {upgrade_type: 'rule_add'}) RETURN count(u) AS c"
        ).single()
        total = total_rec["c"] if total_rec else 0
        rule_add = ra_rec["c"] if ra_rec else 0

    ratio = rule_add / total if total > 0 else 0.0
    report["checks"]["upgrade_rule_add_count"] = rule_add
    report["checks"]["upgrade_total_count"] = total
    report["checks"]["upgrade_rule_add_ratio"] = round(ratio, 3)
    msg = f"Upgrade rule_add: {rule_add}/{total} ({ratio:.1%})"
    if ratio > 0.30:
        report["warnings"].append(f"WARNING — {msg} — exceeds 30% threshold; inspect classifier")
        logger.warning(msg)
    else:
        logger.info(msg)


def _check_dangling_applies_to_profile(driver: neo4j.Driver, report: dict) -> None:
    """Count Upgrade.applies_to_profile values that don't resolve to a Profile node."""
    with driver.session() as session:
        result = session.run(
            """
            MATCH (u:Upgrade)
            WHERE u.applies_to_profile IS NOT NULL
              AND NOT EXISTS { MATCH (p:Profile {id: u.applies_to_profile}) }
            RETURN count(u) AS c
            """
        )
        rec = result.single()
        count = rec["c"] if rec else 0

    report["checks"]["dangling_upgrade_applies_to_profile_count"] = count
    if count > 0:
        logger.warning("Upgrades with unresolved applies_to_profile: %d", count)
    else:
        logger.info("All Upgrade.applies_to_profile references resolve OK")


def _check_armies_without_can_take_item(driver: neo4j.Driver, report: dict) -> None:
    """Flag armies whose units have zero CAN_TAKE_ITEM edges (data anomaly)."""
    with driver.session() as session:
        result = session.run(
            """
            MATCH (a:Army)
            WHERE NOT EXISTS { MATCH (a)<-[:BELONGS_TO]-(u:Unit)-[:CAN_TAKE_ITEM]->() }
            RETURN count(a) AS c
            """
        )
        rec = result.single()
        count = rec["c"] if rec else 0

    report["checks"]["armies_without_can_take_item_count"] = count
    if count > 0:
        logger.warning("Armies with no CAN_TAKE_ITEM edges on any unit: %d", count)
    else:
        logger.info("All armies have at least one CAN_TAKE_ITEM edge OK")


def _check_items_without_army_id_unreachable(driver: neo4j.Driver, report: dict) -> None:
    """Count MagicItems with army_id IS NULL that have no CAN_TAKE_ITEM edges."""
    with driver.session() as session:
        result = session.run(
            """
            MATCH (i:MagicItem)
            WHERE i.army_id IS NULL
              AND NOT EXISTS { MATCH ()-[:CAN_TAKE_ITEM]->(i) }
            RETURN count(i) AS c
            """
        )
        rec = result.single()
        count = rec["c"] if rec else 0

    report["checks"]["null_army_id_unreachable_item_count"] = count
    if count > 0:
        logger.warning("MagicItems with army_id=NULL and no CAN_TAKE_ITEM edges: %d", count)
    else:
        logger.info("All NULL army_id items reachable via CAN_TAKE_ITEM OK")


def _check_faq_errata_coverage(driver: neo4j.Driver, report: dict) -> None:
    """Warn if more than 30 % of FAQ or Errata nodes have zero outgoing CLARIFIES/AMENDS edges."""
    with driver.session() as session:
        faq_total = (session.run("MATCH (f:FAQ) RETURN count(f) AS c").single() or {}).get("c", 0)
        faq_linked = (
            session.run(
                "MATCH (f:FAQ) WHERE EXISTS { (f)-[:CLARIFIES]->() } RETURN count(f) AS c"
            ).single()
            or {}
        ).get("c", 0)
        errata_total = (session.run("MATCH (e:Errata) RETURN count(e) AS c").single() or {}).get(
            "c", 0
        )
        errata_linked = (
            session.run(
                "MATCH (e:Errata) WHERE EXISTS { (e)-[:AMENDS]->() } RETURN count(e) AS c"
            ).single()
            or {}
        ).get("c", 0)

    report["checks"]["faq_total"] = faq_total
    report["checks"]["faq_with_clarifies"] = faq_linked
    report["checks"]["errata_total"] = errata_total
    report["checks"]["errata_with_amends"] = errata_linked

    faq_pct = faq_linked / faq_total if faq_total else 0.0
    errata_pct = errata_linked / errata_total if errata_total else 0.0
    report["checks"]["faq_clarifies_coverage_pct"] = round(faq_pct, 3)
    report["checks"]["errata_amends_coverage_pct"] = round(errata_pct, 3)

    if faq_pct < 0.70:
        msg = f"FAQ CLARIFIES coverage {faq_pct:.1%} ({faq_linked}/{faq_total}) — below 70 % target"
        report["warnings"].append(msg)
        logger.warning(msg)
    else:
        logger.info("FAQ CLARIFIES coverage: %d/%d (%.1%%)", faq_linked, faq_total, faq_pct * 100)

    if errata_pct < 0.70:
        msg = (
            f"Errata AMENDS coverage {errata_pct:.1%} ({errata_linked}/{errata_total})"
            " — below 70 % target"
        )
        report["warnings"].append(msg)
        logger.warning(msg)
    else:
        logger.info(
            "Errata AMENDS coverage: %d/%d (%.1%%)", errata_linked, errata_total, errata_pct * 100
        )


def _check_intrinsic_rule_edges(driver: neo4j.Driver, report: dict) -> None:
    """Warn if no HAS_INTRINSIC_RULE edges exist (TroopType → rule)."""
    with driver.session() as session:
        result = session.run("MATCH ()-[r:HAS_INTRINSIC_RULE]->() RETURN count(r) AS c")
        rec = result.single()
        count = rec["c"] if rec else 0

    report["checks"]["has_intrinsic_rule_count"] = count
    if count == 0:
        msg = "HAS_INTRINSIC_RULE: 0 edges — TroopType intrinsic rule links missing"
        report["warnings"].append(msg)
        logger.warning(msg)
    else:
        logger.info("HAS_INTRINSIC_RULE edges: %d OK", count)


def _check_dangling_troop_types(driver: neo4j.Driver, report: dict) -> None:
    with driver.session() as session:
        result = session.run(
            """
            MATCH (u:Unit)
            WHERE u.troop_type_id IS NOT NULL
              AND NOT EXISTS { MATCH (t:TroopType {id: u.troop_type_id}) }
            RETURN count(u) AS c
            """
        )
        rec = result.single()
        count = rec["c"] if rec else 0

    report["checks"]["dangling_troop_type_id_count"] = count
    if count > 0:
        msg = f"Units with unresolved troop_type_id: {count}"
        report["warnings"].append(msg)
        logger.warning(msg)
    else:
        logger.info("All unit troop_type_id references resolve OK")
