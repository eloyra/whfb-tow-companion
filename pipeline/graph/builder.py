"""
Graph builder orchestrator.

``GraphBuilder().build()`` reads every file from ``data/parsed/``, applies DDL,
loads nodes and edges into Neo4j, seeds static data, and runs the validator.

All write operations are idempotent (MERGE-based), so re-running without
``GRAPH_WIPE_ON_BUILD=true`` produces zero new nodes and zero new edges.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from pipeline.constants import TROOP_TYPE_SEED
from pipeline.graph import client, ddl, loader, seeds, validator

load_dotenv()

logger = logging.getLogger(__name__)

_PARSED_DIR = Path("data/parsed")

# Node files loaded in this order (order is cosmetic — MERGE is order-independent,
# but a stable order makes log output easier to follow).
_NODE_FILES: list[tuple[str, str]] = [
    ("armies.json", "Army"),
    ("composition_lists.json", "CompositionList"),
    ("composition_slots.json", "CompositionSlot"),
    ("troop_types.json", "TroopType"),
    ("units.json", "Unit"),
    ("profiles.json", "Profile"),
    ("upgrades.json", "Upgrade"),
    ("special_rules.json", "SpecialRule"),
    ("core_rules.json", "CoreRule"),
    ("documents.json", "Document"),
    ("lores.json", "Lore"),
    ("spells.json", "Spell"),
    ("weapons.json", "Weapon"),
    ("magic_items.json", "MagicItem"),
    ("faqs.json", "FAQ"),
    ("errata.json", "Errata"),
]


class GraphBuilder:
    """Orchestrates the full graph build pipeline."""

    def build(self) -> dict:
        """Run the full build. Returns the validator report dict."""
        t0 = time.time()
        driver = client.get_driver()

        # Optional: wipe and start fresh
        if os.environ.get("GRAPH_WIPE_ON_BUILD", "false").lower() == "true":
            logger.warning("GRAPH_WIPE_ON_BUILD=true — deleting all nodes and relationships")
            self._wipe(driver)

        # DDL
        ddl.apply_constraints_and_indexes(driver)

        # Seed TroopType rank/strength attrs before loading parsed troop_type nodes,
        # so MERGE-on-id picks them up even when the parsed node carries nulls.
        self._seed_troop_types(driver)

        # Load nodes
        total_nodes = 0
        for filename, label in _NODE_FILES:
            path = _PARSED_DIR / filename
            if not path.exists():
                logger.warning("Parsed file not found, skipping: %s", path)
                continue
            records = json.loads(path.read_text(encoding="utf-8"))
            n = loader.load_nodes(driver, label, records)
            total_nodes += n

        # Load edges
        edges_path = _PARSED_DIR / "edges.json"
        edge_counts: dict[str, int] = {}
        if edges_path.exists():
            edge_records = json.loads(edges_path.read_text(encoding="utf-8"))
            edge_counts = loader.load_edges(driver, edge_records)
        else:
            logger.warning("edges.json not found — skipping edge load")

        # Derived edges: CAN_TAKE_ITEM (requires all nodes + upgrade edges loaded)
        self._derive_can_take_item(driver)

        # Static seeds (no-op when endpoints are missing)
        seeds.seed_alliances(driver)
        seeds.seed_terrain_interactions(driver)

        # Validate
        report = validator.run_all(driver, _PARSED_DIR)

        elapsed = time.time() - t0
        logger.info(
            "Graph build complete in %.1fs — %d nodes, %d edge relations loaded",
            elapsed,
            total_nodes,
            len(edge_counts),
        )
        return report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _wipe(self, driver) -> None:
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            # Drop all user-defined constraints and indexes so DDL recreates them cleanly
            for row in session.run("SHOW CONSTRAINTS"):
                session.run(f"DROP CONSTRAINT {row['name']} IF EXISTS")
            for row in session.run("SHOW INDEXES WHERE type <> 'LOOKUP'"):
                session.run(f"DROP INDEX {row['name']} IF EXISTS")
        logger.info("Graph wiped")

    def _derive_can_take_item(self, driver) -> None:
        """Post-load step: derive CAN_TAKE_ITEM edges from Upgrade + MagicItem data.

        Three MERGE passes (idempotent):
        1. Characters with magic_item_budget or command_bsb → common/army items
           (excluding magic_standard and ability items).
        2. Units with magic_standard_budget → magic_standard items.
        3. Units with vampiric_powers_budget or rune_budget → army-specific ability items.

        Edge properties: budget (int), via_upgrade (str).
        """
        query_items = """
            MATCH (u:Unit)-[:HAS_UPGRADE]->(up:Upgrade)
            WHERE up.upgrade_type IN ['magic_item_budget', 'command_bsb']
            MATCH (u)-[:BELONGS_TO]->(a:Army)
            MATCH (i:MagicItem)
            WHERE (i.army_id IS NULL
                   OR i.army_id IN ['ravening-hordes', 'forces-of-fantasy']
                   OR i.army_id = a.id)
              AND (i.item_type <> 'arcane_item' OR coalesce(u.wizard_level, 0) >= 1)
              AND i.item_type <> 'magic_standard'
              AND i.item_type <> 'ability'
            MERGE (u)-[r:CAN_TAKE_ITEM]->(i)
            ON CREATE SET r.budget = up.points_budget, r.via_upgrade = up.id
        """
        query_standards = """
            MATCH (u:Unit)-[:HAS_UPGRADE]->(up:Upgrade {upgrade_type: 'magic_standard_budget'})
            MATCH (u)-[:BELONGS_TO]->(a:Army)
            MATCH (i:MagicItem {item_type: 'magic_standard'})
            WHERE (i.army_id IS NULL
                   OR i.army_id IN ['ravening-hordes', 'forces-of-fantasy']
                   OR i.army_id = a.id)
            MERGE (u)-[r:CAN_TAKE_ITEM]->(i)
            ON CREATE SET r.budget = up.points_budget, r.via_upgrade = up.id
        """
        query_abilities = """
            MATCH (u:Unit)-[:HAS_UPGRADE]->(up:Upgrade)
            WHERE up.upgrade_type IN ['vampiric_powers_budget', 'rune_budget']
            MATCH (u)-[:BELONGS_TO]->(a:Army)
            MATCH (i:MagicItem {item_type: 'ability'})
            WHERE i.army_id = a.id
            MERGE (u)-[r:CAN_TAKE_ITEM]->(i)
            ON CREATE SET r.budget = up.points_budget, r.via_upgrade = up.id
        """
        with driver.session() as session:
            session.run(query_items)
            session.run(query_standards)
            session.run(query_abilities)
            result = session.run("MATCH ()-[r:CAN_TAKE_ITEM]->() RETURN count(r) AS c")
            count = result.single()["c"]
        logger.info("Derived %d CAN_TAKE_ITEM edges", count)

    def _seed_troop_types(self, driver) -> None:
        """Apply rank-bonus / unit-strength attrs from TROOP_TYPE_SEED.

        TROOP_TYPE_SEED is a dict keyed by slug.  We MERGE on id and SET attrs
        so that if the parsed troop_type node was already loaded (all nulls),
        these values override correctly on any subsequent run too.
        """
        records = [
            {
                "id": slug,
                "min_models_for_rank_bonus": attrs.get("min_models_for_rank_bonus"),
                "max_rank_bonus": attrs.get("max_rank_bonus"),
                "unit_strength_per_model": attrs.get("unit_strength_per_model"),
            }
            for slug, attrs in TROOP_TYPE_SEED.items()
        ]
        query = """
            UNWIND $rows AS row
            MERGE (t:TroopType {id: row.id})
            SET t.min_models_for_rank_bonus = row.min_models_for_rank_bonus,
                t.max_rank_bonus            = row.max_rank_bonus,
                t.unit_strength_per_model   = row.unit_strength_per_model
        """
        with driver.session() as session:
            session.execute_write(lambda tx: tx.run(query, rows=records))
        logger.info("TroopType seed applied (%d entries)", len(records))
