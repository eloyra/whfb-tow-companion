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


class SummaryMetrics(BaseModel):
    """Aggregate metrics across the whole golden set."""

    total_queries: int
    recall_queries: int
    mean_recall_at_k: float | None = None
    mean_correctness: float | None = None
    mean_groundedness: float | None = None
    mean_citation: float | None = None
    below_threshold: list[str] = Field(default_factory=list)
    per_category_recall: dict[str, float] = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    """Top-level report produced by the harness."""

    mode: str
    total_queries: int
    metrics: SummaryMetrics
    results: list[RetrievalResult | AgentResult]
    config: dict[str, Any] = Field(default_factory=dict)


class ComparisonReport(BaseModel):
    """Report comparing retrieval modes on the same golden set (ADR-0008)."""

    modes: list[str]
    total_queries: int
    per_mode: dict[str, SummaryMetrics]
    config: dict[str, Any] = Field(default_factory=dict)
