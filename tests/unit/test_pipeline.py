"""Unit tests for the RAGPipeline orchestrator."""

from __future__ import annotations

from typing import Any

from backend.rag.pipeline import RAGPipeline


class FakeRetriever:
    def __init__(self, seeds: list[dict[str, Any]]) -> None:
        self._seeds = seeds

    def retrieve(self, query: str) -> list[dict[str, Any]]:
        return list(self._seeds)


class FakeTraversal:
    def __init__(
        self,
        expansion: list[dict[str, Any]],
        links: list[dict[str, Any]],
    ) -> None:
        self._expansion = expansion
        self._links = links

    def expand(
        self,
        seed_ids: list[str],
        *,
        max_neighbors_per_seed: int = 6,
    ) -> list[dict[str, Any]]:
        return list(self._expansion)

    def links_between(self, seed_ids: list[str]) -> list[dict[str, Any]]:
        return list(self._links)


def test_query_returns_empty_payload_when_no_seeds() -> None:
    pipeline = RAGPipeline(FakeRetriever([]), FakeTraversal([], []))
    result = pipeline.query("What is the movement of a dragon?")

    assert result["sources"] == []
    assert result["links"] == []
    assert result["expansion"] == []
    assert "No relevant information" in result["context"]


def test_query_formats_context_with_sources_links_and_expansion() -> None:
    seeds = [
        {
            "id": "blood-knights",
            "label": "Unit",
            "name": "Blood Knights",
            "text": "Elite cavalry of the Vampire Counts.",
            "url": "url1",
            "score": 0.95,
        },
        {
            "id": "fear",
            "label": "SpecialRule",
            "name": "Fear",
            "text": "Causes Fear in enemies.",
            "url": "url2",
            "score": 0.88,
        },
    ]
    links = [
        {
            "source": "blood-knights",
            "target": "fear",
            "rel_type": "HAS_RULE",
            "props": {},
        },
    ]
    expansion = [
        {
            "seed_id": "fear",
            "rel_type": "REFERENCES",
            "id": "terror",
            "label": "SpecialRule",
            "name": "Terror",
            "text": "Causes Terror.",
            "url": "url3",
        },
    ]

    pipeline = RAGPipeline(
        FakeRetriever(seeds),
        FakeTraversal(expansion, links),
    )
    result = pipeline.query("Tell me about Blood Knights")

    assert len(result["sources"]) == 2
    assert len(result["links"]) == 1
    assert len(result["expansion"]) == 1

    context = result["context"]
    assert "[blood-knights]" in context
    assert "[fear]" in context
    assert "Blood Knights" in context
    assert "HAS_RULE" in context
    assert "REFERENCES" in context
    assert "## Retrieved sources" in context
    assert "## Direct links among sources" in context
    assert "(1 direct edge(s) among the retrieved sources)" in context
    assert "(Unit)" in context
    assert "(SpecialRule)" in context


def test_neighbor_summary_surfaces_upgrade_cost() -> None:
    """Upgrade nodes (mount options, wargear swaps) have no prose text -- their
    points cost is a bare property and must not be silently dropped."""
    assert RAGPipeline._neighbor_summary("Upgrade", {"points_cost": 16, "cost_unit": "flat"}) == (
        "(+16 pts)"
    )
    assert RAGPipeline._neighbor_summary(
        "Upgrade", {"points_cost": 1, "cost_unit": "per_model"}
    ) == ("(+1 pt/model)")
    assert RAGPipeline._neighbor_summary("Upgrade", {"points_cost": None}) == ""


def test_query_preserves_full_source_text() -> None:
    """Rule text is primary evidence and must never be truncated."""
    long_text = "A" * 600
    seeds = [
        {
            "id": "long-rule",
            "label": "SpecialRule",
            "name": "Long Rule",
            "text": long_text,
            "url": "url",
            "score": 0.9,
        }
    ]
    pipeline = RAGPipeline(FakeRetriever(seeds), FakeTraversal([], []))
    result = pipeline.query("Long rule")
    context = result["context"]

    assert long_text in context
    assert "…" not in context


def test_query_notes_when_no_direct_links_exist() -> None:
    """When there are no links, the context should say so explicitly."""
    seeds = [
        {
            "id": "blood-knights",
            "label": "Unit",
            "name": "Blood Knights",
            "text": "Elite cavalry.",
            "url": "url",
            "score": 0.95,
        }
    ]
    pipeline = RAGPipeline(FakeRetriever(seeds), FakeTraversal([], []))
    result = pipeline.query("Blood Knights")
    context = result["context"]

    assert "## Direct links among sources" in context
    assert "No direct edge was found" in context


class _FakeSession:
    def __init__(self, rows: list[dict[str, Any]], calls: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._calls = calls

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def run(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        self._calls.append({"cypher": cypher, "params": params})
        return self._rows


class _FakeDriver:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.calls: list[dict[str, Any]] = []

    def session(self) -> _FakeSession:
        return _FakeSession(self._rows, self.calls)


class _FakeTraversalWithDriver(FakeTraversal):
    def __init__(self, driver: _FakeDriver) -> None:
        super().__init__([], [])
        self.driver = driver


_ROSTER_ROWS = [
    {
        "army_name": "Vampire Counts",
        "id": "vampire-lord",
        "name": "Vampire Lord",
        "url": "url-lord",
        "unit_category": "Character",
        "army_category": "Characters",
        "cost": 185,
        "size_min": 1,
        "size_max": None,
        "troop_types": ["Infantry"],
    },
    {
        "army_name": "Vampire Counts",
        "id": "skeleton-warriors",
        "name": "Skeleton Warriors",
        "url": "url-skeletons",
        "unit_category": "Infantry",
        "army_category": None,
        "cost": 6,
        "size_min": 10,
        "size_max": None,
        "troop_types": ["Regular Infantry"],
    },
]


def test_list_army_units_returns_roster_payload() -> None:
    driver = _FakeDriver(_ROSTER_ROWS)
    pipeline = RAGPipeline(FakeRetriever([]), _FakeTraversalWithDriver(driver))
    result = pipeline.list_army_units("Vampire Counts")

    assert [src["id"] for src in result["sources"]] == ["vampire-lord", "skeleton-warriors"]
    assert result["links"] == []
    assert result["expansion"] == []

    # Both the display name and its slugified form are passed to Cypher so
    # either input form resolves the army.
    params = driver.calls[0]["params"]
    assert params["army"] == "Vampire Counts"
    assert params["slug"] == "vampire-counts"

    context = result["context"]
    assert "## Units of Vampire Counts (2 entries)" in context
    assert "[skeleton-warriors] Skeleton Warriors: Infantry" in context
    assert "6 pts/model" in context
    assert "unit size 10+" in context
    assert "Core/Special/Rare" in context  # slot caveat surfaced to the model

    # Per-unit text is self-contained (used as the citable block content).
    skeletons = result["sources"][1]
    assert skeletons["text"] == (
        "Skeleton Warriors (Vampire Counts): Infantry; Regular Infantry; "
        "6 pts/model; unit size 10+"
    )


def test_list_army_units_filters_by_category() -> None:
    pipeline = RAGPipeline(
        FakeRetriever([]), _FakeTraversalWithDriver(_FakeDriver(_ROSTER_ROWS))
    )
    result = pipeline.list_army_units("vampire-counts", "characters")

    assert [src["id"] for src in result["sources"]] == ["vampire-lord"]


def test_list_army_units_reports_empty_roster() -> None:
    pipeline = RAGPipeline(FakeRetriever([]), _FakeTraversalWithDriver(_FakeDriver([])))
    result = pipeline.list_army_units("not-an-army")

    assert result["sources"] == []
    assert "No units found" in result["context"]


def test_query_formats_link_props() -> None:
    seeds = [
        {
            "id": "empire-captain",
            "label": "Unit",
            "name": "Empire Captain",
            "text": "",
            "url": "",
            "score": 0.9,
        },
        {
            "id": "blood-drinker",
            "label": "MagicItem",
            "name": "Blood Drinker",
            "text": "",
            "url": "",
            "score": 0.85,
        },
    ]
    links = [
        {
            "source": "empire-captain",
            "target": "blood-drinker",
            "rel_type": "CAN_TAKE_ITEM",
            "props": {"budget": 50, "via_upgrade": "empire-captain-champion"},
        },
    ]

    pipeline = RAGPipeline(FakeRetriever(seeds), FakeTraversal([], links))
    result = pipeline.query("Can an Empire Captain use the Blood Drinker?")

    context = result["context"]
    assert "CAN_TAKE_ITEM" in context
    assert "budget" in context
    assert "50" in context
