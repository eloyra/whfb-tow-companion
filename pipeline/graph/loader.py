"""
Node and edge loader for the Neo4j graph build stage.

All writes are idempotent (MERGE-based) and batched with UNWIND for throughput.
Parsed records are written exactly as-is — all nested structures are already
flattened to scalars at parse time, so ``SET n += row`` is always safe.

Edge loading uses ``apoc.merge.relationship`` with ``MATCH`` (not ``MERGE``) on
both endpoints so that an edge whose source or destination node does not exist is
silently skipped rather than auto-creating a stub node.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Iterator

import neo4j

logger = logging.getLogger(__name__)

_DEFAULT_BATCH = 500
_EDGE_BATCH = 500


def _chunks(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def load_nodes(
    driver: neo4j.Driver,
    label: str,
    records: list[dict],
    batch_size: int = _DEFAULT_BATCH,
) -> int:
    """MERGE nodes of *label* from *records*, return count written.

    Uses ``SET n += row`` to update all properties on match.  Assumes every
    record contains an ``id`` field (the MERGE key).  Records must contain only
    scalar values or lists of scalars — no nested maps.
    """
    if not records:
        return 0

    query = f"""
        UNWIND $rows AS row
        MERGE (n:{label} {{id: row.id}})
        SET n += row
    """
    total = 0
    with driver.session() as session:
        for batch in _chunks(records, batch_size):
            session.execute_write(_run_write, query, rows=batch)
            total += len(batch)

    logger.info("Loaded %d %s nodes", total, label)
    return total


def load_edges(
    driver: neo4j.Driver,
    records: list[dict],
    batch_size: int = _EDGE_BATCH,
) -> dict[str, int]:
    """MERGE edges from *records*, grouped by relation type.

    Returns a dict of ``{relation: count_merged}`` for loaded relations and
    ``{relation: count_skipped}`` for edges whose endpoints were not found.

    Uses ``apoc.merge.relationship`` so the relation type can be dynamic.
    MATCH (not MERGE) on endpoints means a missing node silently drops the edge
    rather than creating a stub — deliberate, per ADR-0004.
    """
    if not records:
        return {}

    by_relation: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        by_relation[rec["relation"]].append(rec)

    query = """
        UNWIND $rows AS row
        MATCH (s {id: row.src})
        MATCH (d {id: row.dst})
        CALL apoc.merge.relationship(s, row.relation, {}, row.properties, d)
        YIELD rel
        RETURN count(rel) AS merged
    """

    counts: dict[str, int] = {}
    with driver.session() as session:
        for relation, rel_records in by_relation.items():
            merged = 0
            for batch in _chunks(rel_records, batch_size):
                result = session.execute_write(_run_write_return, query, rows=batch)
                merged += result
            counts[relation] = merged
            expected = len(rel_records)
            if merged < expected:
                logger.warning(
                    "%s: loaded %d / %d (skipped %d — endpoints missing)",
                    relation,
                    merged,
                    expected,
                    expected - merged,
                )
            else:
                logger.info("%s: loaded %d edges", relation, merged)

    return counts


# ---------------------------------------------------------------------------
# Session helpers (must be top-level functions for execute_write)
# ---------------------------------------------------------------------------


def _run_write(tx: neo4j.ManagedTransaction, query: str, **params: object) -> None:
    tx.run(query, **params)


def _run_write_return(tx: neo4j.ManagedTransaction, query: str, **params: object) -> int:
    result = tx.run(query, **params)
    record = result.single()
    return record["merged"] if record else 0
