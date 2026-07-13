"""Unit tests for the semantic retriever.

Tests use a fake Neo4j driver so no real database is required.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from backend.rag.retriever import RRF_K, GraphRAGRetriever, _lucene_escape
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

    def run(self, query: str, **parameters: Any) -> FakeResult:
        # Parameter named "query" (not "cypher") to match neo4j.Session.run's
        # real signature — a kwarg also named "query" would collide here just
        # as it would against the live driver, catching that class of bug.
        self.queries.append((query, parameters))
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
    retriever = GraphRAGRetriever(
        FakeDriver(responses), FakeEmbedder(), top_k=5, lexical_fallback=True
    )
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
    retriever = GraphRAGRetriever(
        FakeDriver(responses), FakeEmbedder(), top_k=5, lexical_fallback=True
    )
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
    retriever = GraphRAGRetriever(
        FakeDriver(responses), FakeEmbedder(), top_k=5, lexical_fallback=True
    )
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
    retriever = GraphRAGRetriever(
        FakeDriver(responses), FakeEmbedder(), top_k=5, lexical_fallback=True
    )
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
    retriever = GraphRAGRetriever(
        FakeDriver(responses), FakeEmbedder(), top_k=5, lexical_fallback=True
    )
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


def test_lexical_fallback_defaults_to_disabled() -> None:
    """Without explicit ``lexical_fallback=True``, an exact-name match must
    not force a low-scoring node above the top_k cut — the lexical boost is
    a droppable add-on, not the retriever's default behaviour."""
    responses = {
        "SpecialRule": [
            _result("fly", "SpecialRule", "Fly", "Models with this rule can fly.", "url1", 0.10),
        ],
        "Unit": [
            _result("blood-knights", "Unit", "Blood Knights", "Cavalry.", "url2", 0.99),
        ],
    }
    retriever = GraphRAGRetriever(FakeDriver(responses), FakeEmbedder(), top_k=1)
    results = retriever.retrieve("Can a unit with Fly charge over enemy units?")

    assert [r["id"] for r in results] == ["blood-knights"]


def test_invalid_strategy_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unsupported retrieval strategy"):
        GraphRAGRetriever(FakeDriver({}), FakeEmbedder(), strategy="bogus")


def test_hybrid_strategy_fuses_vector_and_fulltext_results() -> None:
    """Hybrid strategy must include nodes found only via full-text search,
    not just the per-label vector pool."""

    class HybridSession:
        def __init__(
            self, vector_responses: dict[str, list[dict[str, Any]]], fulltext_rows: list
        ) -> None:
            self._vector_responses = vector_responses
            self._fulltext_rows = fulltext_rows

        def __enter__(self) -> "HybridSession":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def run(self, query: str, **params: Any) -> FakeResult:
            # Parameter named "query" to match neo4j.Session.run's real
            # signature — see FakeSession.run above.
            if "fulltext" in query:
                return FakeResult(self._fulltext_rows)
            return FakeResult(self._vector_responses.get(params.get("label", ""), []))

    class HybridDriver:
        def __init__(
            self, vector_responses: dict[str, list[dict[str, Any]]], fulltext_rows: list
        ) -> None:
            self._vector_responses = vector_responses
            self._fulltext_rows = fulltext_rows

        def session(self) -> HybridSession:
            return HybridSession(self._vector_responses, self._fulltext_rows)

    vector_responses = {
        "SpecialRule": [
            _result("fear", "SpecialRule", "Fear", "Causes Fear.", "url1", 0.95),
        ],
    }
    fulltext_rows = [
        _result("terror", "SpecialRule", "Terror", "Causes Terror.", "url2", 5.0),
    ]
    retriever = GraphRAGRetriever(
        HybridDriver(vector_responses, fulltext_rows),
        FakeEmbedder(),
        top_k=5,
        strategy="hybrid",
    )
    results = retriever.retrieve("Fear and Terror")

    assert {r["id"] for r in results} == {"fear", "terror"}


def test_fuse_rrf_ranks_nodes_present_in_both_lists_higher() -> None:
    """A node ranked #2 in one list and #1 in the other should outrank a node
    ranked #1 in only a single list — that's the point of RRF over either
    ranking alone."""
    vector_ranked = [
        {"id": "a", "score": 0.9},
        {"id": "b", "score": 0.5},
    ]
    fulltext_ranked = [
        {"id": "b", "score": 12.0},
        {"id": "c", "score": 8.0},
    ]
    fused = GraphRAGRetriever._fuse_rrf(vector_ranked, fulltext_ranked, k_const=60)

    ids = [r["id"] for r in fused]
    assert ids[0] == "b"
    assert set(ids) == {"a", "b", "c"}

    expected_b_score = 1 / (60 + 2) + 1 / (60 + 1)
    assert fused[0]["score"] == pytest.approx(expected_b_score)


def test_fuse_rrf_score_replaces_original_score() -> None:
    """The fused score is rank-based, not the original cosine/BM25 value —
    the two scales are incomparable, so mixing them would be meaningless."""
    fused = GraphRAGRetriever._fuse_rrf([{"id": "a", "score": 0.99}], [])
    assert fused[0]["score"] == pytest.approx(1 / (RRF_K + 1))


def test_lucene_escape_escapes_question_mark_and_parens() -> None:
    escaped = _lucene_escape("What is the Stubborn (Ld) rule?")
    assert escaped == r"What is the Stubborn \(Ld\) rule\?"


def test_lucene_escape_escapes_colon_and_wildcards() -> None:
    escaped = _lucene_escape("field:value AND wild*card?")
    assert "\\:" in escaped
    assert "\\*" in escaped
    assert "\\?" in escaped
