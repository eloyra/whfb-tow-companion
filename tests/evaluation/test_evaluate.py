"""Unit tests for the evaluation harness scoring and dataset helpers.

These tests are intentionally free of Neo4j and LLM dependencies so they can
run in the normal pytest suite and act as a CI gate for the evaluation code.
"""

from __future__ import annotations

from langchain.chat_models import BaseChatModel
from langchain.messages import AIMessage
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult

from tests.evaluation.dataset import load_queries
from tests.evaluation.models import AgentResult, JudgeVerdict, Query, RetrievalResult
from tests.evaluation.runner import _extract_cited_ids_from_tool_message
from tests.evaluation.scoring import (
    aggregate_metrics,
    army_retrieved,
    build_retrieval_result,
    citation_coverage,
    recall_at_k,
)


class StubJudgeLLM(BaseChatModel):
    """Fake LLM that returns a fixed judge verdict JSON."""

    verdict_json: str = '{"correctness": 2, "groundedness": 1, "citation": 2, "notes": "ok"}'

    def _llm_type(self) -> str:
        return "stub-judge"

    def _generate(self, messages: list[BaseMessage], **kwargs: object) -> ChatResult:
        raise NotImplementedError

    async def _agenerate(self, messages: list[BaseMessage], **kwargs: object) -> ChatResult:
        raise NotImplementedError

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: object = None,
        **kwargs: object,
    ):
        yield ChatGenerationChunk(message=AIMessage(content=self.verdict_json))


class TestRecallAtK:
    def test_perfect_recall(self) -> None:
        assert recall_at_k(["a", "b"], ["a", "b", "c"]) == 1.0

    def test_partial_recall(self) -> None:
        assert recall_at_k(["a", "b", "d"], ["a", "c"]) == 1 / 3

    def test_respects_k(self) -> None:
        assert recall_at_k(["a", "b"], ["a", "b", "c"], k=2) == 1.0
        assert recall_at_k(["b"], ["a", "b", "c"], k=1) == 0.0

    def test_empty_expected_returns_none(self) -> None:
        assert recall_at_k([], ["a", "b"]) is None


class TestArmyRetrieved:
    def test_present(self) -> None:
        assert army_retrieved("vampire-counts", ["fear", "vampire-counts"]) is True

    def test_absent(self) -> None:
        assert army_retrieved("empire-of-man", ["fear", "blood-knights"]) is False

    def test_no_expected_returns_none(self) -> None:
        assert army_retrieved(None, ["fear"]) is None


class TestCitationCoverage:
    def test_perfect(self) -> None:
        assert citation_coverage(["a", "b"], ["a", "b"]) == 1.0

    def test_partial(self) -> None:
        assert citation_coverage(["a", "b", "c"], ["a"]) == 1 / 3

    def test_empty_expected_returns_none(self) -> None:
        assert citation_coverage([], ["a"]) is None


class TestBuildRetrievalResult:
    def test_basic_result(self) -> None:
        result = build_retrieval_result(
            query_id="q001",
            query="What is Fear?",
            category="rule_lookup",
            expected_rules=["fear"],
            expected_army=None,
            retrieved=["fear", "terror"],
            k=8,
        )
        assert result.query_id == "q001"
        assert result.recall_at_k == 1.0
        assert result.army_retrieved is None

    def test_open_ended_ignored(self) -> None:
        result = build_retrieval_result(
            query_id="q026",
            query="Build a list",
            category="army_building",
            expected_rules=[],
            expected_army="vampire-counts",
            retrieved=["vampire-counts", "blood-knights"],
            k=8,
        )
        assert result.recall_at_k is None
        assert result.army_retrieved is True


class TestExtractCitedIds:
    def test_reads_artifact_first(self) -> None:
        """Native path: sources live on .artifact, never inline in content."""
        msg = ToolMessage(
            content=[{"type": "search_result", "title": "Fear", "source": "..."}],
            artifact={"context": "...", "sources": [{"id": "fear"}, {"id": "stubborn"}]},
            tool_call_id="call_1",
        )
        assert _extract_cited_ids_from_tool_message(msg) == ["fear", "stubborn"]

    def test_falls_back_to_legacy_json_content(self) -> None:
        """No artifact: fall back to parsing the JSON-string content."""
        msg = ToolMessage(
            content='{"context": "...", "sources": [{"id": "fear"}]}',
            tool_call_id="call_1",
        )
        assert _extract_cited_ids_from_tool_message(msg) == ["fear"]

    def test_invalid_content_returns_empty(self) -> None:
        msg = ToolMessage(content="not-json", tool_call_id="call_1")
        assert _extract_cited_ids_from_tool_message(msg) == []


class TestAggregateMetrics:
    def test_retrieval_only(self) -> None:
        results = [
            RetrievalResult(
                query_id="q1",
                query="...",
                category="rule_lookup",
                retrieved_ids=["a"],
                expected_rules=["a"],
                expected_army=None,
                recall_at_k=1.0,
                army_retrieved=None,
            ),
            RetrievalResult(
                query_id="q2",
                query="...",
                category="rule_lookup",
                retrieved_ids=["a"],
                expected_rules=["a", "b"],
                expected_army=None,
                recall_at_k=0.5,
                army_retrieved=None,
            ),
        ]
        metrics = aggregate_metrics(results, recall_threshold=0.6)
        assert metrics.mean_recall_at_k == 0.75
        assert metrics.below_threshold == ["q2"]

    def test_with_judge_verdict(self) -> None:
        results = [
            AgentResult(
                query_id="q1",
                query="...",
                category="rule_lookup",
                answer="yes",
                cited_ids=["a"],
                expected_rules=["a"],
                expected_army=None,
                retrieval=RetrievalResult(
                    query_id="q1",
                    query="...",
                    category="rule_lookup",
                    retrieved_ids=["a"],
                    expected_rules=["a"],
                    expected_army=None,
                    recall_at_k=1.0,
                    army_retrieved=None,
                ),
                verdict=JudgeVerdict(correctness=2, groundedness=2, citation=2),
            )
        ]
        metrics = aggregate_metrics(results, recall_threshold=0.5, judge_threshold=1.5)
        assert metrics.mean_correctness == 2.0
        assert metrics.mean_groundedness == 2.0
        assert metrics.mean_citation == 2.0
        assert metrics.below_threshold == []


class TestDataset:
    def test_loads_all_queries(self) -> None:
        queries = load_queries()
        assert len(queries) == 70
        assert all(isinstance(q, Query) for q in queries)
        assert queries[0].id == "q001"

    def test_all_expected_rules_are_strings(self) -> None:
        queries = load_queries()
        for q in queries:
            assert isinstance(q.expected_rules, list)
            assert all(isinstance(r, str) for r in q.expected_rules)

    def test_no_duplicate_ids(self) -> None:
        queries = load_queries()
        ids = [q.id for q in queries]
        assert len(ids) == len(set(ids))
