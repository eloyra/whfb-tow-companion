"""Unit tests for the semantic retriever.

Tests use a fake Neo4j driver so no real database is required.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from backend.rag.retriever import GraphRAGRetriever
from pipeline.constants import EMBEDDABLE_LABELS


class FakeRecord:
    """Minimal Record-like object for the fake session."""

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
    """Captures queries and returns canned records per label."""

    def __init__(self, responses: dict[str, list[dict[str, Any]]]) -> None:
        self._responses = responses
        self.queries: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def run(self, cypher: str, **parameters: Any) -> FakeResult:
        self.queries.append((cypher, parameters))
        label = parameters.get("label", "")
        return FakeResult(self._responses.get(label, []))


class FakeDriver:
    def __init__(self, responses: dict[str, list[dict[str, Any]]]) -> None:
        self._responses = responses

    def session(self) -> FakeSession:
        return FakeSession(self._responses)


class FakeEmbedder:
    """Returns a deterministic 768-d vector (list) for any input."""

    def encode(self, text: str, **kwargs: Any) -> list[float]:
        return [0.1] * 768


def _result(
    node_id: str,
    label: str,
    name: str,
    text: str,
    url: str,
    score: float,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": label,
        "name": name,
        "text": text,
        "url": url,
        "score": score,
    }


def test_retrieve_merges_across_labels_and_dedup() -> None:
    responses = {
        "Unit": [
            _result("blood-knights", "Unit", "Blood Knights", "Fast cavalry.", "url1", 0.95),
        ],
        "SpecialRule": [
            _result("fear", "SpecialRule", "Fear", "Causes Fear.", "url2", 0.92),
            # Duplicate id appearing in a second label with lower score should be ignored.
            _result("blood-knights", "SpecialRule", "Blood Knights", "Rule.", "url3", 0.50),
        ],
    }
    retriever = GraphRAGRetriever(FakeDriver(responses), FakeEmbedder(), top_k=5)
    # Use a query with no exact node-name phrase so the lexical fallback stays
    # silent and this test isolates pure vector-score dedup behaviour.
    results = retriever.retrieve("Tell me about these cavalry riders")

    assert len(results) == 2
    assert results[0]["id"] == "blood-knights"
    assert results[0]["score"] == 0.95
    assert results[1]["id"] == "fear"


def test_retrieve_top_k_limits_results() -> None:
    responses = {
        label: [
            _result(
                f"{label.lower()}-node",
                label,
                f"{label} Name",
                "Text.",
                "url",
                0.9 - i * 0.01,
            )
        ]
        for i, label in enumerate(EMBEDDABLE_LABELS)
    }
    retriever = GraphRAGRetriever(FakeDriver(responses), FakeEmbedder(), top_k=3)
    results = retriever.retrieve("query")

    assert len(results) == 3
    # Highest scores first.
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_coalesces_missing_text_to_name() -> None:
    responses = {
        "Army": [
            {
                "id": "vampire-counts",
                "label": "Army",
                "name": "Vampire Counts",
                "text": None,
                "url": "url",
                "score": 0.88,
            }
        ],
    }
    retriever = GraphRAGRetriever(FakeDriver(responses), FakeEmbedder(), top_k=5)
    results = retriever.retrieve("Vampire Counts army")

    assert results[0]["text"] == "Vampire Counts"


def test_retrieve_lexical_match_forces_inclusion() -> None:
    """A node whose exact name appears in the query is included even if it
    never surfaces in the (mocked) vector-search pool at all."""
    responses = {
        "SpecialRule": [
            _result("fly", "SpecialRule", "Fly", "Models with this rule can fly.", "url1", 0.10),
        ],
    }
    retriever = GraphRAGRetriever(FakeDriver(responses), FakeEmbedder(), top_k=5)
    results = retriever.retrieve("Can a unit with Fly charge over enemy units?")

    ids = [r["id"] for r in results]
    assert "fly" in ids
    fly_result = next(r for r in results if r["id"] == "fly")
    assert fly_result["score"] == 1.0


def test_retrieve_lexical_match_strips_parenthetical_placeholder() -> None:
    """Variable-value special rules are stored as "Fly (X)"; a plain-language
    query saying just "Fly" (no value) should still match."""
    responses = {
        "SpecialRule": [
            _result(
                "fly", "SpecialRule", "Fly (X)", "Models with this rule can fly.", "url1", 0.10
            ),
        ],
    }
    retriever = GraphRAGRetriever(FakeDriver(responses), FakeEmbedder(), top_k=5)
    results = retriever.retrieve("Can a unit with Fly charge over enemy units?")

    fly_result = next(r for r in results if r["id"] == "fly")
    assert fly_result["score"] == 1.0


def test_retrieve_lexical_match_stems_multiword_names() -> None:
    """Multi-word names match a different inflection in the query: "Disrupted
    Units" should match a query phrased as "disrupts units"."""
    responses = {
        "CoreRule": [
            _result(
                "disrupted-units",
                "CoreRule",
                "Disrupted Units",
                "A unit becomes Disrupted if...",
                "url1",
                0.10,
            ),
        ],
    }
    retriever = GraphRAGRetriever(FakeDriver(responses), FakeEmbedder(), top_k=5)
    results = retriever.retrieve("What terrain disrupts units?")

    result = next(r for r in results if r["id"] == "disrupted-units")
    assert result["score"] == 1.0


def test_retrieve_lexical_match_single_word_does_not_stem() -> None:
    """Single-word names must NOT stem-match: stemming "Fly" would also
    swallow the unrelated word "flying"."""
    responses = {
        "SpecialRule": [
            _result("fly", "SpecialRule", "Fly", "Models with this rule can fly.", "url1", 0.10),
        ],
    }
    retriever = GraphRAGRetriever(FakeDriver(responses), FakeEmbedder(), top_k=5)
    results = retriever.retrieve("Tell me about butterfly wings on a flying carpet")

    fly_result = next(r for r in results if r["id"] == "fly")
    assert fly_result["score"] == 0.10


def test_retrieve_lexical_match_is_word_boundary_only() -> None:
    """A short node name must not false-positive on a substring of a longer,
    unrelated word in the query — score should stay at the raw vector value,
    not get boosted to the lexical-match score."""
    responses = {
        "SpecialRule": [
            _result("fly", "SpecialRule", "Fly", "Models with this rule can fly.", "url1", 0.10),
        ],
    }
    retriever = GraphRAGRetriever(FakeDriver(responses), FakeEmbedder(), top_k=5)
    results = retriever.retrieve("Tell me about butterfly wings on a flying carpet")

    fly_result = next(r for r in results if r["id"] == "fly")
    assert fly_result["score"] == 0.10


def test_retrieve_skips_failed_label_and_continues(caplog: pytest.LogCaptureFixture) -> None:
    class FailingSession:
        def __enter__(self) -> "FailingSession":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def run(self, **kwargs: Any) -> FakeResult:
            raise RuntimeError("index missing")

    class FailingDriver:
        def session(self) -> FailingSession:
            return FailingSession()

    # Use a driver that fails for every label so only the exception handling path is exercised.
    retriever = GraphRAGRetriever(FailingDriver(), FakeEmbedder(), top_k=5)
    with caplog.at_level(logging.WARNING):
        results = retriever.retrieve("query")

    assert results == []
    assert any("Vector query failed" in rec.message for rec in caplog.records)
