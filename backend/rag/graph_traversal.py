"""Bounded graph traversal to enrich retrieved seed nodes.

Two operations are exposed:

1. ``expand()`` — bounded 1-hop neighborhood context. Returns related rules,
   mounts, items, profiles, etc. around each seed. Used for "tell me more about
   this node" and "what can X ride/take?".

2. ``links_between()`` — direct edges **among** the retrieved seeds. This is the
   graph-reasoning primitive that answers eligibility/capability questions such
   as "can an empire captain use the blood drinker sword?" or "can an orc boss
   ride a dragon?" where both the subject and the object are returned as seeds.

Deeper multi-hop reasoning is intentionally left to the LangGraph agent: if the
first-pass context is insufficient, the agent issues a follow-up tool call with a
refined query (another set of seeds + another traversal).
"""

from __future__ import annotations

from typing import Any

import neo4j

# Relationship types followed by ``expand()``, grouped by explanatory value.
# Lower tier number = higher priority when the per-seed cap binds.
_EDGE_TYPE_TIERS: dict[str, int] = {
    # Multi-hop semantic links (the core of GraphRAG rules reasoning)
    "REFERENCES": 0,
    "CLARIFIES": 0,
    "AMENDS": 0,
    # Unit/rule/terrain interactions + equipment/mount eligibility
    "HAS_RULE": 1,
    "HAS_OPTIONAL_RULE": 1,
    "HAS_INTRINSIC_RULE": 1,
    "TERRAIN_INTERACTION": 1,
    "CAN_MOUNT": 1,
    "CAN_TAKE_ITEM": 1,
    # Structural context and equipment/upgrades
    "HAS_PROFILE": 2,
    "HAS_TYPE": 2,
    "BELONGS_TO": 2,
    "BELONGS_TO_LORE": 2,
    "HAS_WEAPON": 2,
    "HAS_UPGRADE": 2,
    "UNLOCKS_ITEM": 2,
    "UNLOCKS_WEAPON": 2,
    "UNLOCKS_MOUNT": 2,
    "REPLACES_WEAPON": 2,
}

_EDGE_TYPES = list(_EDGE_TYPE_TIERS.keys())

# Warhammer is a densely interconnected ruleset by design (units interact with
# rules, terrain, mounts, magic items, upgrades — that density is exactly what
# GraphRAG exists to exploit, versus flat vector RAG). A single relation type
# can vastly outnumber the others for a given seed (a spellcaster is eligible
# for 100-250+ CAN_TAKE_ITEM magic items; a well-referenced rule can have
# dozens of REFERENCES), which — sorted into one shared per-seed cap — used to
# silently starve every other relation type (e.g. a Vampire Count's ~14
# HAS_UPGRADE mount/equipment options, each carrying a points cost, never
# surfaced at all once one high-volume type filled the whole budget). Each
# type gets its own cap instead, so a single tool call returns breadth across
# rules/mounts/items/upgrades rather than depth in just one of them — the
# agent should rarely need a follow-up call to see "what interacts with this."
_DEFAULT_PER_RELATION_CAP = 4
_MAX_PER_RELATION_TYPE: dict[str, int] = {
    "CAN_TAKE_ITEM": 3,  # by far the largest possible fan-out; kept tightest
    "REFERENCES": 5,  # can also run into the dozens for heavily cross-linked rules
    # A unit's own purchase options (mounts, wargear, command group, magic
    # item/standard budgets) — bounded by what's actually on that unit's page
    # (rarely more than ~20 even for the most loaded characters), unlike
    # CAN_TAKE_ITEM's external pool of every eligible item in the game. Kept
    # high rather than tightly capped: these are exactly the numbers "how much
    # does X cost" questions need, and dropping half of them to an arbitrary
    # alphabetical tie-break defeats the point of raising the cap at all.
    "HAS_UPGRADE": 20,
}


def expand(
    driver: neo4j.Driver,
    seed_ids: list[str],
    *,
    max_neighbors_per_seed: int = 40,
) -> list[dict[str, Any]]:
    """Return bounded, ranked 1-hop neighbors for ``seed_ids``.

    Each returned dict has keys:
    ``seed_id``, ``rel_type``, ``id``, ``label``, ``name``, ``text``, ``url``.
    Neighbors are deduplicated per seed and ranked by relationship tier (semantic
    links first). Each relation type is capped independently (see
    ``_MAX_PER_RELATION_TYPE``) before the overall ``max_neighbors_per_seed``
    ceiling is applied, so breadth across types isn't sacrificed to depth in
    whichever type happens to have the most edges.
    """
    if not seed_ids:
        return []

    rows = _fetch_neighbors(driver, seed_ids)

    # Group by seed id and rank/cap per seed.
    grouped: dict[str, list[dict[str, Any]]] = {sid: [] for sid in seed_ids}
    for row in rows:
        sid = row["seed_id"]
        grouped[sid].append(row)

    results: list[dict[str, Any]] = []
    for sid in seed_ids:
        neighbors = grouped[sid]
        neighbors.sort(key=_neighbor_priority)
        neighbors = _cap_per_relation_type(neighbors)
        results.extend(neighbors[:max_neighbors_per_seed])

    return results


def _cap_per_relation_type(neighbors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop excess rows per relation type, using ``_MAX_PER_RELATION_TYPE``
    (falling back to ``_DEFAULT_PER_RELATION_CAP`` for any type not listed).

    Applied after priority sort, so the surviving rows for a capped type are
    still its highest-priority ones (alphabetically first, tier ties aside).
    """
    counts: dict[str, int] = {}
    kept: list[dict[str, Any]] = []
    for row in neighbors:
        limit = _MAX_PER_RELATION_TYPE.get(row["rel_type"], _DEFAULT_PER_RELATION_CAP)
        counts[row["rel_type"]] = counts.get(row["rel_type"], 0) + 1
        if counts[row["rel_type"]] > limit:
            continue
        kept.append(row)
    return kept


def links_between(
    driver: neo4j.Driver,
    seed_ids: list[str],
) -> list[dict[str, Any]]:
    """Return direct edges among ``seed_ids``.

    Each returned dict has keys:
    ``source``, ``target``, ``rel_type``, ``props``.
    Undirected edges are deduplicated so each pair is returned once.

    This is the key query for eligibility/capability questions where both the
    subject and the object are semantically retrieved as seeds (e.g. "can X use
    Y?", "can X ride Y?", "are X and Y allies?").
    """
    if not seed_ids:
        return []

    cypher = """
        MATCH (a)-[r]-(b)
        WHERE a.id IN $seed_ids AND b.id IN $seed_ids AND a.id <> b.id
        RETURN a.id AS source, b.id AS target, type(r) AS rel_type, properties(r) AS props
    """
    with driver.session() as session:
        result = session.run(cypher, seed_ids=seed_ids)
        rows = [dict(record) for record in result]

    # Undirected MATCH returns each edge twice; dedupe by (min_id, max_id, rel_type).
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(sorted((row["source"], row["target"]))) + (row["rel_type"],)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    return deduped


def _fetch_neighbors(
    driver: neo4j.Driver,
    seed_ids: list[str],
) -> list[dict[str, Any]]:
    """Run one batched Cypher query for all seeds."""
    cypher = """
        UNWIND $seed_ids AS sid
        MATCH (seed {id: sid})-[r]-(neighbor)
        WHERE type(r) IN $edge_types AND NOT neighbor.id IN $seed_ids
        RETURN seed.id AS seed_id,
               type(r) AS rel_type,
               labels(neighbor)[0] AS label,
               neighbor.id AS id,
               neighbor.name AS name,
               coalesce(neighbor.text, neighbor.name, '') AS text,
               neighbor.url AS url,
               neighbor.points_cost AS points_cost,
               neighbor.cost_unit AS cost_unit
    """
    with driver.session() as session:
        result = session.run(
            cypher,
            seed_ids=seed_ids,
            edge_types=_EDGE_TYPES,
        )
        rows = [dict(record) for record in result]

    # Python-side coalesce guards against records where both text and name are None.
    for row in rows:
        row["text"] = row.get("text") or row.get("name") or ""
    return rows


def _neighbor_priority(row: dict[str, Any]) -> tuple[int, str]:
    """Sort key: tier first, then stable id ordering."""
    tier = _EDGE_TYPE_TIERS.get(row["rel_type"], 99)
    return (tier, row["id"])


class GraphTraversal:
    """Driver-bound wrapper exposing a retriever-like API.

    This mirrors ``GraphRAGRetriever``: the dependency layer injects a driver
    once, and the pipeline calls ``expand()`` / ``links_between()`` without
    needing to pass the driver on every call.
    """

    def __init__(self, driver: neo4j.Driver) -> None:
        self.driver = driver

    def expand(
        self,
        seed_ids: list[str],
        *,
        max_neighbors_per_seed: int = 40,
    ) -> list[dict[str, Any]]:
        """Return bounded, ranked 1-hop neighbors for ``seed_ids``."""
        return expand(
            self.driver,
            seed_ids,
            max_neighbors_per_seed=max_neighbors_per_seed,
        )

    def links_between(self, seed_ids: list[str]) -> list[dict[str, Any]]:
        """Return direct edges among ``seed_ids``."""
        return links_between(self.driver, seed_ids)
