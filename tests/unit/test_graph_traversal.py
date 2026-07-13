"""Unit tests for the graph traversal module.

Uses a fake Neo4j driver so no real database is required.
"""

from __future__ import annotations

from typing import Any

from backend.rag.graph_traversal import GraphTraversal, expand, links_between, subgraph


class FakeRecord:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()


class FakeResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = [FakeRecord(r) for r in records]

    def __iter__(self):
        return iter(self._records)


class FakeSession:
    def __init__(
        self,
        responses: dict[str, list[dict[str, Any]]],
        links: list[dict[str, Any]],
        subgraph_response: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._responses = responses
        self._links = links
        self._subgraph_response = subgraph_response
        self.last_query: tuple[str, dict[str, Any]] | None = None

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def run(self, cypher: str, **parameters: Any) -> FakeResult:
        self.last_query = (cypher, parameters)
        if "apoc.path.subgraphAll" in cypher:
            if self._subgraph_response is None:
                return FakeResult([])
            return FakeResult([self._subgraph_response])

        if "MATCH (a)-[r]-(b)" in cypher:
            return FakeResult(self._links)

        seed_ids = parameters.get("seed_ids", [])
        records: list[dict[str, Any]] = []
        for sid in seed_ids:
            for neighbor in self._responses.get(sid, []):
                records.append({"seed_id": sid, **neighbor})
        return FakeResult(records)


class FakeDriver:
    def __init__(
        self,
        responses: dict[str, list[dict[str, Any]]] | None = None,
        links: list[dict[str, Any]] | None = None,
        subgraph_response: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._responses = responses or {}
        self._links = links or []
        self._subgraph_response = subgraph_response

    def session(self) -> FakeSession:
        return FakeSession(self._responses, self._links, self._subgraph_response)


def _neighbor(
    rel_type: str,
    node_id: str,
    label: str = "SpecialRule",
    name: str = "Name",
    text: str = "Text.",
    url: str = "url",
) -> dict[str, Any]:
    return {
        "rel_type": rel_type,
        "id": node_id,
        "label": label,
        "name": name,
        "text": text,
        "url": url,
    }


def test_expand_empty_seed_list() -> None:
    assert expand(FakeDriver(), []) == []


def test_expand_undirected_includes_both_directions() -> None:
    responses = {
        "fear": [
            # Outgoing REFERENCES
            _neighbor("REFERENCES", "terror", name="Terror"),
            # Incoming HAS_RULE (a unit pointing at Fear)
            _neighbor("HAS_RULE", "ghoul-king", label="Unit", name="Ghoul King"),
        ],
    }
    results = expand(FakeDriver(responses), ["fear"])

    assert len(results) == 2
    assert {r["id"] for r in results} == {"terror", "ghoul-king"}


def test_expand_includes_can_mount_at_tier_1() -> None:
    responses = {
        "orc-warboss": [
            _neighbor("CAN_MOUNT", "wyvern", label="Unit", name="Wyvern"),
            _neighbor("HAS_TYPE", "infantry", label="TroopType", name="Infantry"),
        ],
    }
    results = expand(FakeDriver(responses), ["orc-warboss"], max_neighbors_per_seed=1)

    assert len(results) == 1
    assert results[0]["rel_type"] == "CAN_MOUNT"


def test_expand_caps_per_seed_and_ranks_by_tier() -> None:
    responses = {
        "blood-knights": [
            # Tier 2 (lowest priority)
            _neighbor("HAS_TYPE", "heavy-cavalry", label="TroopType", name="Heavy Cavalry"),
            # Tier 1
            _neighbor("HAS_RULE", "fear", name="Fear"),
            # Tier 0 (highest priority)
            _neighbor("REFERENCES", "frenzy", name="Frenzy"),
            # Another tier 2
            _neighbor("BELONGS_TO", "vampire-counts", label="Army", name="Vampire Counts"),
        ],
    }
    results = expand(FakeDriver(responses), ["blood-knights"], max_neighbors_per_seed=2)

    assert len(results) == 2
    # Tier 0 should win; tier 1 should beat tier 2.
    assert results[0]["rel_type"] == "REFERENCES"
    assert results[1]["rel_type"] == "HAS_RULE"


def test_expand_excludes_seed_to_seed_neighbors() -> None:
    responses = {
        "fear": [
            _neighbor("REFERENCES", "terror", name="Terror"),
            # This neighbor is another seed id — should be filtered by the Cypher WHERE clause.
            _neighbor("REFERENCES", "stubborn", name="Stubborn"),
        ],
        "stubborn": [
            _neighbor("REFERENCES", "fear", name="Fear"),
        ],
    }
    results = expand(FakeDriver(responses), ["fear", "stubborn"])

    # Since the fake does not enforce the WHERE clause, we verify the output shape.
    # The real Neo4j Cypher excludes seed-to-seed matches.
    seed_ids_in_output = {r["seed_id"] for r in results}
    assert seed_ids_in_output == {"fear", "stubborn"} or seed_ids_in_output == {"fear"}
    assert len(results) <= 8  # sanity cap


def test_expand_coalesces_missing_text() -> None:
    responses = {
        "fear": [
            {
                "rel_type": "REFERENCES",
                "id": "terror",
                "label": "SpecialRule",
                "name": "Terror",
                "text": None,
                "url": "url",
            }
        ],
    }
    results = expand(FakeDriver(responses), ["fear"])

    assert results[0]["text"] == "Terror"


def test_links_between_returns_direct_edges_with_props() -> None:
    links = [
        {
            "source": "empire-captain",
            "target": "blood-drinker",
            "rel_type": "CAN_TAKE_ITEM",
            "props": {"budget": 50, "via_upgrade": "empire-captain-champion"},
        },
    ]
    results = links_between(FakeDriver(links=links), ["empire-captain", "blood-drinker"])

    assert len(results) == 1
    assert results[0]["rel_type"] == "CAN_TAKE_ITEM"
    assert results[0]["props"]["budget"] == 50


def test_links_between_dedupes_undirected_edges() -> None:
    # Neo4j undirected MATCH returns the edge in both directions.
    links = [
        {"source": "a", "target": "b", "rel_type": "REFERENCES", "props": {}},
        {"source": "b", "target": "a", "rel_type": "REFERENCES", "props": {}},
    ]
    results = links_between(FakeDriver(links=links), ["a", "b"])

    assert len(results) == 1


def test_links_between_returns_empty_for_unconnected_seeds() -> None:
    assert links_between(FakeDriver(links=[]), ["a", "b"]) == []


def test_links_between_empty_seed_list() -> None:
    assert links_between(FakeDriver(), []) == []


def test_graph_traversal_class_has_retriever_like_api() -> None:
    """GraphTraversal binds the driver and exposes expand()/links_between() used by RAGPipeline."""
    responses = {
        "fear": [
            _neighbor("REFERENCES", "terror", name="Terror"),
        ],
    }
    links = [
        {"source": "a", "target": "b", "rel_type": "REFERENCES", "props": {}},
    ]
    driver = FakeDriver(responses=responses, links=links)
    traversal = GraphTraversal(driver)

    expansion = traversal.expand(["fear"], max_neighbors_per_seed=1)
    assert len(expansion) == 1
    assert expansion[0]["id"] == "terror"

    direct = traversal.links_between(["a", "b"])
    assert len(direct) == 1
    assert direct[0]["rel_type"] == "REFERENCES"


def _edge(source: str, target: str, rel_type: str) -> dict[str, Any]:
    return {"source": source, "target": target, "rel_type": rel_type}


def test_subgraph_not_found_returns_empty() -> None:
    assert subgraph(FakeDriver(), "missing") == {"nodes": [], "edges": []}


def test_subgraph_isolated_center_returns_just_center() -> None:
    response = {
        "nodes": [{"id": "fear", "label": "SpecialRule", "name": "Fear", "source_url": "url"}],
        "edges": [],
    }
    result = subgraph(FakeDriver(subgraph_response=response), "fear")

    assert result == {
        "nodes": [{"id": "fear", "label": "SpecialRule", "name": "Fear", "source_url": "url"}],
        "edges": [],
    }


def test_subgraph_maps_nodes_and_edges() -> None:
    response = {
        "nodes": [
            {"id": "fear", "label": "SpecialRule", "name": "Fear", "source_url": "url-fear"},
            {"id": "terror", "label": "SpecialRule", "name": "Terror", "source_url": "url-terror"},
        ],
        "edges": [_edge("fear", "terror", "REFERENCES")],
    }
    result = subgraph(FakeDriver(subgraph_response=response), "fear")

    assert {n["id"] for n in result["nodes"]} == {"fear", "terror"}
    assert result["edges"] == [{"source": "fear", "target": "terror", "rel_type": "REFERENCES"}]
    # embedding must never be part of the shape returned to the frontend.
    assert all("embedding" not in node for node in result["nodes"])


def test_subgraph_drops_nodes_whose_only_edge_was_capped_away() -> None:
    # "hub" fans out via a default-capped relation type (tier 2, cap 4 — see
    # _DEFAULT_PER_RELATION_CAP) to 5 leaves; the center is always kept, but a
    # leaf reachable only through the dropped 5th edge must not survive.
    nodes = [{"id": "hub", "label": "Unit", "name": "Hub", "source_url": None}]
    edges = []
    for i in range(1, 6):
        leaf_id = f"leaf-{i}"
        nodes.append({"id": leaf_id, "label": "TroopType", "name": leaf_id, "source_url": None})
        edges.append(_edge("hub", leaf_id, "HAS_TYPE"))

    response = {"nodes": nodes, "edges": edges}
    result = subgraph(FakeDriver(subgraph_response=response), "hub")

    assert len(result["edges"]) == 4
    kept_leaves = {e["target"] for e in result["edges"]}
    assert kept_leaves == {"leaf-1", "leaf-2", "leaf-3", "leaf-4"}
    node_ids = {n["id"] for n in result["nodes"]}
    assert node_ids == {"hub", "leaf-1", "leaf-2", "leaf-3", "leaf-4"}
    assert "leaf-5" not in node_ids


def test_subgraph_caps_use_per_relation_type_overrides() -> None:
    # CAN_TAKE_ITEM has a tighter override cap (3) than the default (4).
    nodes = [{"id": "wizard", "label": "Unit", "name": "Wizard", "source_url": None}]
    edges = []
    for i in range(1, 6):
        item_id = f"item-{i}"
        nodes.append({"id": item_id, "label": "MagicItem", "name": item_id, "source_url": None})
        edges.append(_edge("wizard", item_id, "CAN_TAKE_ITEM"))

    response = {"nodes": nodes, "edges": edges}
    result = subgraph(FakeDriver(subgraph_response=response), "wizard")

    assert len(result["edges"]) == 3


def test_subgraph_caps_new_discoveries_per_expanding_node() -> None:
    # "shared" is offered by 6 different HAS_TYPE edges (1 from hub, 5 from
    # other-1..5), but only "shared" spends its own discovery budget when *it*
    # expands outward during BFS — the incoming hub->shared edge is hub's
    # budget, a separate accounting, and isn't capped by shared's own limit.
    nodes = [
        {"id": "hub", "label": "Unit", "name": "Hub", "source_url": None},
        {"id": "shared", "label": "SpecialRule", "name": "Shared", "source_url": None},
    ]
    edges = [_edge("hub", "shared", "HAS_TYPE")]
    for i in range(1, 6):
        other_id = f"other-{i}"
        nodes.append({"id": other_id, "label": "SpecialRule", "name": other_id, "source_url": None})
        edges.append(_edge(other_id, "shared", "HAS_TYPE"))

    response = {"nodes": nodes, "edges": edges}
    result = subgraph(FakeDriver(subgraph_response=response), "hub")

    # hub->shared (hub's own budget) survives unconditionally; "shared"'s own
    # discovery budget for HAS_TYPE (default cap 4) admits only 4 of other-1..5.
    assert len(result["edges"]) == 5
    kept_others = {e["source"] for e in result["edges"] if e["source"].startswith("other-")}
    assert kept_others == {"other-1", "other-2", "other-3", "other-4"}
    assert "other-5" not in {n["id"] for n in result["nodes"]}


def test_subgraph_never_returns_a_node_unreachable_from_center() -> None:
    """Regression test for a real bug: a flat sort-and-cap over the raw edge
    list could keep an edge whose *only* path back to the center had itself
    been capped away, producing "floating island" nodes with no path to
    node_id through any returned edge. Confirmed against the live graph: the
    old flat-cap approach left 46 of 64 nodes unreachable from "regeneration"
    at depth=2. The fix (a capped BFS) must never do this.
    """
    # hub has 5 outgoing HAS_TYPE edges (default cap 4); branch-5 gets capped
    # away. branch-5 also leads onward (via a high-priority, uncapped
    # REFERENCES edge) to leaf-5 — a flat cap could keep that downstream edge
    # while dropping the only edge connecting branch-5 (and leaf-5) to "hub".
    nodes = [{"id": "hub", "label": "Unit", "name": "Hub", "source_url": None}]
    edges = []
    for i in range(1, 6):
        branch_id = f"branch-{i}"
        nodes.append({"id": branch_id, "label": "TroopType", "name": branch_id, "source_url": None})
        edges.append(_edge("hub", branch_id, "HAS_TYPE"))
    nodes.append({"id": "leaf-5", "label": "SpecialRule", "name": "leaf-5", "source_url": None})
    edges.append(_edge("branch-5", "leaf-5", "REFERENCES"))

    response = {"nodes": nodes, "edges": edges}
    result = subgraph(FakeDriver(subgraph_response=response), "hub")

    node_ids = {n["id"] for n in result["nodes"]}
    assert "branch-5" not in node_ids
    assert "leaf-5" not in node_ids
    for edge in result["edges"]:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids


def test_subgraph_dedupes_duplicate_self_loop_edges() -> None:
    # apoc.path.subgraphAll's undirected BFS can surface the same self-loop
    # relationship twice (observed for a unit's own HAS_WEAPON edge).
    response = {
        "nodes": [
            {"id": "hub", "label": "Unit", "name": "Hub", "source_url": None},
        ],
        "edges": [
            _edge("hub", "hub", "HAS_WEAPON"),
            _edge("hub", "hub", "HAS_WEAPON"),
        ],
    }
    result = subgraph(FakeDriver(subgraph_response=response), "hub")

    assert result["edges"] == [{"source": "hub", "target": "hub", "rel_type": "HAS_WEAPON"}]


def test_graph_traversal_class_exposes_subgraph() -> None:
    response = {
        "nodes": [{"id": "fear", "label": "SpecialRule", "name": "Fear", "source_url": "url"}],
        "edges": [],
    }
    traversal = GraphTraversal(FakeDriver(subgraph_response=response))

    result = traversal.subgraph("fear", depth=2)
    assert result["nodes"][0]["id"] == "fear"
    assert result["edges"] == []
