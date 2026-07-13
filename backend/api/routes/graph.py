"""Graph-exploration REST endpoints backing the frontend graph viewer.

Two endpoints:

- ``GET /graph/nodes`` — search/browse entry point. With ``node_type``, lists
  nodes of that label. Without it, a name-prefix search across every
  embeddable label (mirrors ``GraphRAGRetriever._fetch_name_index``'s
  label-loop shape).
- ``GET /graph/subgraph/{node_id}`` — bounded multi-hop neighborhood around a
  single node (``backend/rag/graph_traversal.py::subgraph``).

Both endpoints go through the shared Neo4j driver via ``Depends(get_driver)``
(no fresh connection) and never interpolate raw query-string input into
Cypher label position — ``node_type`` is validated against
``pipeline.constants.NODE_TYPE_TO_LABEL`` first, exactly like the retriever's
label handling.
"""

from __future__ import annotations

import logging

import neo4j
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.api.dependencies import get_driver
from backend.rag import graph_traversal
from pipeline.constants import EMBEDDABLE_LABELS, NODE_TYPE_TO_LABEL

logger = logging.getLogger(__name__)

router = APIRouter()


class GraphNode(BaseModel):
    """A node as shown by the graph viewer. ``embedding`` is never included."""

    id: str
    label: str | None = None
    name: str | None = None
    source_url: str | None = None


class GraphEdge(BaseModel):
    """A directed edge as shown by the graph viewer."""

    source: str
    target: str
    rel_type: str


class NodeListResponse(BaseModel):
    nodes: list[GraphNode]


class SubgraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


def _fetch_nodes_for_label(
    driver: neo4j.Driver,
    label: str,
    name_prefix: str | None,
    limit: int,
) -> list[GraphNode]:
    """Fetch up to ``limit`` nodes of ``label``, optionally name-prefix filtered.

    ``label`` must come from a hard-coded allow-list (``NODE_TYPE_TO_LABEL``
    values / ``EMBEDDABLE_LABELS``) — never interpolate raw user input into the
    label position. This mirrors ``GraphRAGRetriever._fetch_name_index``: one
    query per label, with a per-label try/except so a single failing label
    doesn't abort the whole request.
    """
    if limit <= 0:
        return []
    try:
        cypher = f"MATCH (n:{label}) WHERE n.name IS NOT NULL "
        if name_prefix:
            cypher += "AND toLower(n.name) STARTS WITH toLower($name_prefix) "
        cypher += "RETURN n.id AS id, n.name AS name, n.url AS source_url LIMIT $limit"
        with driver.session() as session:
            result = session.run(cypher, name_prefix=name_prefix, limit=limit)
            return [
                GraphNode(id=r["id"], label=label, name=r["name"], source_url=r["source_url"])
                for r in result
            ]
    except Exception as exc:  # noqa: BLE001 — log and continue with other labels
        logger.warning("Node fetch failed for label %s: %s", label, exc)
        return []


@router.get("/nodes", response_model=NodeListResponse)
async def get_nodes(
    node_type: str | None = Query(None),
    q: str | None = Query(None, description="Case-insensitive name-prefix filter"),
    limit: int = Query(100, le=1000),
    driver: neo4j.Driver = Depends(get_driver),
) -> NodeListResponse:
    if node_type is not None:
        label = NODE_TYPE_TO_LABEL.get(node_type.lower())
        if label is None:
            supported = ", ".join(sorted(NODE_TYPE_TO_LABEL.keys()))
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported node_type '{node_type}'. Use one of: {supported}",
            )
        return NodeListResponse(nodes=_fetch_nodes_for_label(driver, label, q, limit))

    # No node_type: this is the graph viewer's search/browse entry point —
    # a name-prefix search across every embeddable label.
    nodes: list[GraphNode] = []
    for label in EMBEDDABLE_LABELS:
        remaining = limit - len(nodes)
        if remaining <= 0:
            break
        nodes.extend(_fetch_nodes_for_label(driver, label, q, remaining))
    return NodeListResponse(nodes=nodes)


@router.get("/subgraph/{node_id}", response_model=SubgraphResponse)
async def get_subgraph(
    node_id: str,
    depth: int = Query(2, le=4),
    driver: neo4j.Driver = Depends(get_driver),
) -> SubgraphResponse:
    result = graph_traversal.subgraph(driver, node_id, depth=depth)
    return SubgraphResponse(
        nodes=[GraphNode(**node) for node in result["nodes"]],
        edges=[GraphEdge(**edge) for edge in result["edges"]],
    )
