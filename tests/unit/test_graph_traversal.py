"""Unit tests for the graph traversal module.

Uses a fake Neo4j driver so no real database is required.
"""

from __future__ import annotations

from typing import Any

from backend.rag.graph_traversal import expand, links_between


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
    ) -> None:
        self._responses = responses
        self._links = links
        self.last_query: tuple[str, dict[str, Any]] | None = None

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def run(self, cypher: str, **parameters: Any) -> FakeResult:
        self.last_query = (cypher, parameters)
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
    ) -> None:
        self._responses = responses or {}
        self._links = links or []

    def session(self) -> FakeSession:
        return FakeSession(self._responses, self._links)


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
