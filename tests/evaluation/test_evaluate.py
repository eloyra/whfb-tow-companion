"""Unit tests for the evaluation harness scoring and dataset helpers.

These tests are intentionally free of Neo4j and LLM dependencies so they can
run in the normal pytest suite and act as a CI gate for the evaluation code.
"""

from __future__ import annotations

import pytest
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
    citation_f1,
    citation_precision,
    f1_at_k,
    hop_bucket,
    mrr,
    ndcg_at_k,
    paired_significance,
    per_category_recall,
    per_hop_metrics,
    precision_at_k,
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


class TestPrecisionAtK:
    def test_perfect(self) -> None:
        assert precision_at_k(["a", "b"], ["a", "b"]) == 1.0

    def test_partial(self) -> None:
        # 1 of 3 retrieved ids is relevant.
        assert precision_at_k(["a"], ["a", "b", "c"]) == 1 / 3

    def test_respects_k(self) -> None:
        assert precision_at_k(["a"], ["b", "a", "c"], k=1) == 0.0
        assert precision_at_k(["a"], ["a", "b", "c"], k=1) == 1.0

    def test_empty_expected_returns_none(self) -> None:
        assert precision_at_k([], ["a"]) is None

    def test_empty_retrieved_returns_none(self) -> None:
        """No prediction was made, so precision is undefined, not zero."""
        assert precision_at_k(["a"], []) is None


class TestF1AtK:
    def test_harmonic_mean_of_precision_and_recall(self) -> None:
        # expected=[a,b], retrieved=[a,c]: precision=1/2, recall=1/2 -> f1=0.5
        assert f1_at_k(["a", "b"], ["a", "c"]) == 0.5

    def test_zero_precision_and_recall_gives_zero_not_nan(self) -> None:
        assert f1_at_k(["a"], ["b"]) == 0.0

    def test_empty_expected_returns_none(self) -> None:
        assert f1_at_k([], ["a"]) is None


class TestCitationPrecisionAndF1:
    def test_citation_precision_penalizes_over_citing(self) -> None:
        """Citing everything gives perfect coverage but poor precision --
        precision is what catches that failure mode."""
        assert citation_coverage(["a"], ["a", "b", "c", "d"]) == 1.0
        assert citation_precision(["a"], ["a", "b", "c", "d"]) == 1 / 4

    def test_citation_precision_none_when_nothing_cited(self) -> None:
        assert citation_precision(["a"], []) is None

    def test_citation_f1_combines_both_directions(self) -> None:
        assert citation_f1(["a", "b"], ["a", "c"]) == 0.5


class TestMRR:
    def test_hit_at_first_rank(self) -> None:
        assert mrr(["a"], ["a", "b", "c"]) == 1.0

    def test_hit_at_third_rank(self) -> None:
        assert mrr(["a"], ["x", "y", "a"]) == 1 / 3

    def test_no_hit_is_zero_not_none(self) -> None:
        """Unlike recall_at_k, a genuine miss on a non-empty expected set is
        0.0 (a real answer of "never found it"), not None."""
        assert mrr(["a"], ["x", "y", "z"]) == 0.0

    def test_empty_expected_returns_none(self) -> None:
        assert mrr([], ["a"]) is None


class TestNdcgAtK:
    def test_perfect_ranking_is_one(self) -> None:
        assert ndcg_at_k(["a", "b"], ["a", "b", "c"]) == 1.0

    def test_later_rank_scores_lower_than_earlier(self) -> None:
        early = ndcg_at_k(["a"], ["a", "x", "y"])
        late = ndcg_at_k(["a"], ["x", "y", "a"])
        assert early == 1.0
        assert 0 < late < early

    def test_empty_expected_returns_none(self) -> None:
        assert ndcg_at_k([], ["a"]) is None

    def test_empty_retrieved_returns_none(self) -> None:
        assert ndcg_at_k(["a"], []) is None


class TestHopBucket:
    def test_buckets_by_expected_rules_length(self) -> None:
        assert hop_bucket([]) == "0"
        assert hop_bucket(["a"]) == "1"
        assert hop_bucket(["a", "b"]) == "2"
        assert hop_bucket(["a", "b", "c"]) == "3+"
        assert hop_bucket(["a", "b", "c", "d"]) == "3+"


class TestPairedSignificance:
    def test_all_positive_deltas_is_significant(self) -> None:
        deltas = [0.2, 0.3, 0.25, 0.4, 0.1, 0.35, 0.2, 0.3]
        result = paired_significance(deltas)
        assert result["n"] == len(deltas)
        assert result["p_value"] < 0.05

    def test_identical_modes_all_zero_deltas_not_significant(self) -> None:
        result = paired_significance([0.0, 0.0, 0.0])
        assert result["p_value"] == 1.0

    def test_empty_deltas(self) -> None:
        result = paired_significance([])
        assert result["n"] == 0
        assert result["p_value"] == 1.0


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
        assert result.precision_at_k == 1 / 2
        assert result.f1_at_k == pytest.approx(2 / 3)
        assert result.mrr == 1.0
        assert result.ndcg_at_k == 1.0
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
        assert result.precision_at_k is None
        assert result.f1_at_k is None
        assert result.mrr is None
        assert result.ndcg_at_k is None
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
                citation_precision=1.0,
                citation_f1=1.0,
                answer_hit=True,
            )
        ]
        metrics = aggregate_metrics(results, recall_threshold=0.5, judge_threshold=1.5)
        assert metrics.mean_correctness == 2.0
        assert metrics.mean_groundedness == 2.0
        assert metrics.mean_citation == 2.0
        assert metrics.mean_citation_precision == 1.0
        assert metrics.mean_citation_f1 == 1.0
        assert metrics.answer_hit_rate == 1.0
        assert metrics.below_threshold == []

    def test_answer_hit_rate_mixed(self) -> None:
        def _agent(query_id: str, hit: bool) -> AgentResult:
            return AgentResult(
                query_id=query_id,
                query="...",
                category="rule_lookup",
                answer="...",
                cited_ids=[],
                expected_rules=["a"],
                expected_army=None,
                verdict=JudgeVerdict(correctness=2 if hit else 0, groundedness=1, citation=1),
                answer_hit=hit,
            )

        results = [_agent("q1", True), _agent("q2", False)]
        metrics = aggregate_metrics(results)
        assert metrics.answer_hit_rate == 0.5


class TestPerCategoryRecall:
    def test_groups_by_category_and_skips_none(self) -> None:
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
            RetrievalResult(
                query_id="q3",
                query="...",
                category="army_building",
                retrieved_ids=[],
                expected_rules=[],
                expected_army="vampire-counts",
                recall_at_k=None,
                army_retrieved=True,
            ),
        ]
        assert per_category_recall(results) == {"rule_lookup": 0.75}

    def test_empty_results_returns_empty_dict(self) -> None:
        assert per_category_recall([]) == {}


class TestPerHopMetrics:
    def test_groups_by_hop_bucket(self) -> None:
        results = [
            build_retrieval_result(
                query_id="q1",
                query="...",
                category="rule_lookup",
                expected_rules=["a"],
                expected_army=None,
                retrieved=["a"],
            ),
            build_retrieval_result(
                query_id="q2",
                query="...",
                category="rule_interaction",
                expected_rules=["a", "b"],
                expected_army=None,
                retrieved=["a"],
            ),
        ]
        metrics = per_hop_metrics(results)
        assert metrics["1"]["recall"] == 1.0
        assert metrics["2"]["recall"] == 0.5
        assert "0" not in metrics  # no zero-hop query in this fixture

    def test_open_ended_bucket_excluded_when_no_data(self) -> None:
        """Hop bucket "0" (no expected_rules) has no recall/precision/f1 by
        definition, so it should not appear as an empty entry."""
        results = [
            build_retrieval_result(
                query_id="q1",
                query="...",
                category="army_building",
                expected_rules=[],
                expected_army="vampire-counts",
                retrieved=["vampire-counts"],
            ),
        ]
        assert per_hop_metrics(results) == {}


class TestDataset:
    def test_loads_all_queries(self) -> None:
        queries = load_queries()
        assert len(queries) == 100
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
