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
