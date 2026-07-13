"""Pydantic models for the RAG evaluation harness."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Query(BaseModel):
    """A single golden-set query with its expected answer metadata."""

    id: str
    language: str
    query: str
    category: str
    expected_rules: list[str] = Field(default_factory=list)
    expected_army: str | None = None
    rubric: str


class RetrievalResult(BaseModel):
    """Retrieval metrics for one query."""

    query_id: str
    query: str
    category: str
    retrieved_ids: list[str]
    expected_rules: list[str]
    expected_army: str | None = None
    recall_at_k: float | None = None
    precision_at_k: float | None = None
    f1_at_k: float | None = None
    mrr: float | None = None
    ndcg_at_k: float | None = None
    army_retrieved: bool | None = None


class JudgeVerdict(BaseModel):
    """Structured output from the LLM-judge."""

    correctness: int = Field(ge=0, le=2, description="0-2 score for factual correctness")
    groundedness: int = Field(ge=0, le=2, description="0-2 score for grounding in sources")
    citation: int = Field(ge=0, le=2, description="0-2 score for citation quality")
    notes: str = ""


class AgentResult(BaseModel):
    """Full agent result for one query."""

    query_id: str
    query: str
    category: str
    answer: str
    cited_ids: list[str]
    expected_rules: list[str]
    expected_army: str | None = None
    retrieval: RetrievalResult | None = None
    verdict: JudgeVerdict | None = None
    citation_precision: float | None = None
    citation_f1: float | None = None
    answer_hit: bool | None = None


class SummaryMetrics(BaseModel):
    """Aggregate metrics across the whole golden set."""

    total_queries: int
    recall_queries: int
    mean_recall_at_k: float | None = None
    mean_precision_at_k: float | None = None
    mean_f1_at_k: float | None = None
    mean_mrr: float | None = None
    mean_ndcg_at_k: float | None = None
    mean_correctness: float | None = None
    mean_groundedness: float | None = None
    mean_citation: float | None = None
    mean_citation_precision: float | None = None
    mean_citation_f1: float | None = None
    answer_hit_rate: float | None = None
    below_threshold: list[str] = Field(default_factory=list)
    per_category_recall: dict[str, float] = Field(default_factory=dict)
    per_hop_metrics: dict[str, dict[str, float]] = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    """Top-level report produced by the harness."""

    mode: str
    total_queries: int
    metrics: SummaryMetrics
    results: list[RetrievalResult | AgentResult]
    config: dict[str, Any] = Field(default_factory=dict)


class SignificanceResult(BaseModel):
    """Paired statistical-significance test between two retrieval modes (ADR-0008).

    Wilcoxon signed-rank test on per-query metric deltas across the shared golden
    set — the two modes are evaluated on the *same* queries, so the comparison is
    paired, not independent samples.
    """

    mode_a: str
    mode_b: str
    metric: str
    statistic: float
    p_value: float
    n: int
    significant: bool


class ComparisonReport(BaseModel):
    """Report comparing retrieval modes on the same golden set (ADR-0008)."""

    modes: list[str]
    total_queries: int
    per_mode: dict[str, SummaryMetrics]
    significance: list[SignificanceResult] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
