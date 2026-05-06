"""
Static seed data applied after the main graph load.

Seeds use MERGE so they are idempotent and no-op-safe when endpoints do not
exist (e.g. :Terrain nodes are not yet ingested — terrain seed writes zero edges).

Source:
- ALLIANCE_SEED: schema docs/schema/knowledge_graph_schema.md L786 (partial).
- TERRAIN_INTERACTION_SEED: schema L814 (partial).

Expanding either list to full coverage is a separate tracking task.
"""

from __future__ import annotations

import logging

import neo4j

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Alliance seed (partial — expand from each army's Grand Army composition page)
# ---------------------------------------------------------------------------

ALLIANCE_SEED: list[dict] = [
    # Vampire Counts
    {"from": "vampire-counts", "to": "tomb-kings-of-khemri", "alliance_type": "trusted"},
    # Empire of Man
    {"from": "empire-of-man", "to": "dwarfen-mountain-holds", "alliance_type": "trusted"},
    {"from": "empire-of-man", "to": "grand-cathay", "alliance_type": "trusted"},
    {"from": "empire-of-man", "to": "kingdom-of-bretonnia", "alliance_type": "trusted"},
    {"from": "empire-of-man", "to": "wood-elf-realms", "alliance_type": "suspicious"},
]

# ---------------------------------------------------------------------------
# Terrain interaction seed (partial — expand from special rule text parsing)
# ---------------------------------------------------------------------------

TERRAIN_INTERACTION_SEED: list[dict] = [
    # Fly (X): ignores most terrain during movement
    {
        "from_label": "SpecialRule",
        "from_id": "fly",
        "to_id": "difficult-terrain",
        "effect": "ignores",
    },
    {
        "from_label": "SpecialRule",
        "from_id": "fly",
        "to_id": "dangerous-terrain",
        "effect": "ignores_dangerous_test",
    },
    {"from_label": "SpecialRule", "from_id": "fly", "to_id": "woods", "effect": "ignores"},
    # Ethereal: ignores all terrain
    {
        "from_label": "SpecialRule",
        "from_id": "ethereal",
        "to_id": "difficult-terrain",
        "effect": "ignores",
    },
    {
        "from_label": "SpecialRule",
        "from_id": "ethereal",
        "to_id": "dangerous-terrain",
        "effect": "ignores",
    },
    {
        "from_label": "SpecialRule",
        "from_id": "ethereal",
        "to_id": "impassable-terrain",
        "effect": "ignores",
    },
    # Move Through Cover: ignores cover from woods
    {
        "from_label": "SpecialRule",
        "from_id": "move-through-cover",
        "to_id": "woods",
        "effect": "ignores_cover",
    },
    # Scouts: can deploy in woods
    {"from_label": "SpecialRule", "from_id": "scouts", "to_id": "woods", "effect": "can_deploy_in"},
    # Skirmishers: treat woods as open
    {
        "from_label": "SpecialRule",
        "from_id": "skirmishers",
        "to_id": "woods",
        "effect": "ignores_disruption",
    },
]


def seed_alliances(driver: neo4j.Driver) -> int:
    """Apply ALLIED_WITH edges from ALLIANCE_SEED. Returns count written."""
    query = """
        MATCH (a:Army {id: $from_id}), (b:Army {id: $to_id})
        MERGE (a)-[e:ALLIED_WITH]->(b)
        SET e.alliance_type = $alliance_type
        RETURN count(e) AS written
    """
    written = 0
    with driver.session() as session:
        for entry in ALLIANCE_SEED:
            result = session.run(
                query,
                from_id=entry["from"],
                to_id=entry["to"],
                alliance_type=entry["alliance_type"],
            )
            rec = result.single()
            written += rec["written"] if rec else 0
    logger.info("Alliance seed: %d ALLIED_WITH edges written", written)
    return written


def seed_terrain_interactions(driver: neo4j.Driver) -> int:
    """Apply TERRAIN_INTERACTION edges from TERRAIN_INTERACTION_SEED. Returns count written."""
    written = 0
    with driver.session() as session:
        for entry in TERRAIN_INTERACTION_SEED:
            query = f"""
                MATCH (source:{entry["from_label"]} {{id: $from_id}}), (t:Terrain {{id: $to_id}})
                MERGE (source)-[e:TERRAIN_INTERACTION]->(t)
                SET e.effect = $effect
                RETURN count(e) AS written
            """
            result = session.run(
                query,
                from_id=entry["from_id"],
                to_id=entry["to_id"],
                effect=entry["effect"],
            )
            rec = result.single()
            written += rec["written"] if rec else 0
    logger.info("Terrain seed: %d TERRAIN_INTERACTION edges written", written)
    return written
