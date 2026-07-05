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


def expand(
    driver: neo4j.Driver,
    seed_ids: list[str],
    *,
    max_neighbors_per_seed: int = 6,
) -> list[dict[str, Any]]:
    """Return bounded, ranked 1-hop neighbors for ``seed_ids``.

    Each returned dict has keys:
    ``seed_id``, ``rel_type``, ``id``, ``label``, ``name``, ``text``, ``url``.
    Neighbors are deduplicated per seed and ranked by relationship tier (semantic
    links first); at most ``max_neighbors_per_seed`` are kept per seed.
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
        results.extend(neighbors[:max_neighbors_per_seed])

    return results


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
               neighbor.url AS url
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
        max_neighbors_per_seed: int = 6,
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
