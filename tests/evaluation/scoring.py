"""Pure scoring functions for the evaluation harness.

These functions are intentionally free of side effects and I/O so they can be
unit-tested without Neo4j or an LLM.
"""

from __future__ import annotations

from tests.evaluation.models import AgentResult, RetrievalResult, SummaryMetrics


def recall_at_k(expected: list[str], retrieved: list[str], k: int | None = None) -> float | None:
    """Return the fraction of ``expected`` ids present in ``retrieved``.

    If ``expected`` is empty, ``None`` is returned so the query can be excluded
    from aggregate recall (e.g. open-ended army-building queries).

    Args:
        expected: Ground-truth node ids that should be retrieved.
        retrieved: Node ids returned by the retriever (ordered by score).
        k: Optional cutoff; if provided, only the first ``k`` retrieved ids are
            considered. If ``None``, all retrieved ids are considered.
    """
    if not expected:
        return None
    pool = retrieved if k is None else retrieved[:k]
    pool_set = set(pool)
    hits = sum(1 for node_id in expected if node_id in pool_set)
    return hits / len(expected)


def army_retrieved(expected_army: str | None, retrieved: list[str]) -> bool | None:
    """Check whether the expected army id appears among retrieved nodes.

    Returns ``None`` when no army is expected.
    """
    if expected_army is None:
        return None
    return expected_army in set(retrieved)


def citation_coverage(expected: list[str], cited: list[str]) -> float | None:
    """Return the fraction of ``expected`` ids that were cited in the answer.

    Returns ``None`` when there are no expected rules to cite.
    """
    if not expected:
        return None
    cited_set = set(cited)
    hits = sum(1 for node_id in expected if node_id in cited_set)
    return hits / len(expected)


def build_retrieval_result(
    query_id: str,
    query: str,
    category: str,
    expected_rules: list[str],
    expected_army: str | None,
    retrieved: list[str],
    k: int | None = None,
) -> RetrievalResult:
    """Construct a ``RetrievalResult`` with recall and army flags computed."""
    return RetrievalResult(
        query_id=query_id,
        query=query,
        category=category,
        retrieved_ids=retrieved,
        expected_rules=expected_rules,
        expected_army=expected_army,
        recall_at_k=recall_at_k(expected_rules, retrieved, k),
        army_retrieved=army_retrieved(expected_army, retrieved),
    )


def per_category_recall(results: list[RetrievalResult | AgentResult]) -> dict[str, float]:
    """Mean recall@k grouped by query ``category``, skipping ``None`` values.

    Lets the comparison report show *where* a retrieval mode wins or loses
    (e.g. hybrid helping "rule_interaction" queries but not "army_building"),
    which a single overall mean recall obscures.
    """
    by_category: dict[str, list[float]] = {}
    for result in results:
        is_agent = isinstance(result, AgentResult)
        retrieval = result.retrieval if is_agent else result
        if isinstance(retrieval, RetrievalResult) and retrieval.recall_at_k is not None:
            by_category.setdefault(result.category, []).append(retrieval.recall_at_k)
    return {cat: sum(vals) / len(vals) for cat, vals in sorted(by_category.items())}


def aggregate_metrics(
    results: list[RetrievalResult | AgentResult],
    recall_threshold: float = 0.5,
    judge_threshold: float = 1.0,
) -> SummaryMetrics:
    """Compute aggregate metrics and flag queries below thresholds.

    Only results with a non-``None`` metric contribute to its mean. Queries
    whose recall or mean judge score falls below the threshold are listed in
    ``below_threshold``.
    """
    recall_values: list[float] = []
    correctness: list[float] = []
    groundedness: list[float] = []
    citation: list[float] = []
    below: list[str] = []

    for result in results:
        is_agent = isinstance(result, AgentResult)
        retrieval = result.retrieval if is_agent else result
        verdict = result.verdict if is_agent else None

        if isinstance(retrieval, RetrievalResult) and retrieval.recall_at_k is not None:
            recall_values.append(retrieval.recall_at_k)
            if retrieval.recall_at_k < recall_threshold:
                below.append(result.query_id)

        if verdict is not None:
            correctness.append(verdict.correctness)
            groundedness.append(verdict.groundedness)
            citation.append(verdict.citation)
            mean_judge = (verdict.correctness + verdict.groundedness + verdict.citation) / 3
            if mean_judge < judge_threshold:
                below.append(result.query_id)

    def _mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    return SummaryMetrics(
        total_queries=len(results),
        recall_queries=len(recall_values),
        mean_recall_at_k=_mean(recall_values),
        mean_correctness=_mean(correctness),
        mean_groundedness=_mean(groundedness),
        mean_citation=_mean(citation),
        below_threshold=sorted(set(below)),
        per_category_recall=per_category_recall(results),
    )
