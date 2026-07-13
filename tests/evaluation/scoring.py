"""Pure scoring functions for the evaluation harness.

These functions are intentionally free of side effects and I/O so they can be
unit-tested without Neo4j or an LLM.
"""

from __future__ import annotations

import math

from tests.evaluation.models import AgentResult, RetrievalResult, SummaryMetrics


def _f1(precision: float | None, recall: float | None) -> float | None:
    """Harmonic mean of ``precision`` and ``recall``, ``None`` if either is."""
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


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


def precision_at_k(expected: list[str], retrieved: list[str], k: int | None = None) -> float | None:
    """Return the fraction of the (top-``k``) retrieved ids that are ``expected``.

    Mirrors ``recall_at_k``'s null-handling: ``None`` when ``expected`` is empty
    (nothing could be correct or incorrect) or when the pool is empty (no
    prediction was made, so precision is undefined rather than zero).
    """
    if not expected:
        return None
    pool = retrieved if k is None else retrieved[:k]
    if not pool:
        return None
    expected_set = set(expected)
    hits = sum(1 for node_id in pool if node_id in expected_set)
    return hits / len(pool)


def f1_at_k(expected: list[str], retrieved: list[str], k: int | None = None) -> float | None:
    """Harmonic mean of ``precision_at_k`` and ``recall_at_k``."""
    return _f1(precision_at_k(expected, retrieved, k), recall_at_k(expected, retrieved, k))


def mrr(expected: list[str], retrieved: list[str]) -> float | None:
    """Reciprocal rank of the first relevant id in ``retrieved`` (1-based).

    Unlike ``recall_at_k``, a miss is a genuine ``0.0`` (not ``None``) once
    ``expected`` is non-empty: the question of "how early was the first hit"
    has a real answer of "never" when there is no hit, which recall's
    "not applicable" null convention doesn't need to express.
    """
    if not expected:
        return None
    expected_set = set(expected)
    for rank, node_id in enumerate(retrieved, start=1):
        if node_id in expected_set:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(expected: list[str], retrieved: list[str], k: int | None = None) -> float | None:
    """Normalized Discounted Cumulative Gain at ``k`` (binary relevance).

    Rewards relevant ids appearing earlier in ``retrieved``, unlike
    ``recall_at_k``/``precision_at_k`` which treat every rank within the cutoff
    identically.
    """
    if not expected:
        return None
    pool = retrieved if k is None else retrieved[:k]
    if not pool:
        return None
    expected_set = set(expected)
    dcg = sum(1.0 / math.log2(i + 2) for i, node_id in enumerate(pool) if node_id in expected_set)
    ideal_hits = min(len(expected_set), len(pool))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg else 0.0


def hop_bucket(expected_rules: list[str]) -> str:
    """Bucket a query by its reasoning-hop-count proxy: ``len(expected_rules)``.

    A query needing to combine N ground-truth rules to be answered correctly
    is a reasonable proxy for N-hop reasoning complexity, and this is already
    present in the golden set with no new annotation needed. Buckets: ``"0"``
    (open-ended, no fixed expected rules), ``"1"`` (single-concept lookup),
    ``"2"``, ``"3+"`` (multi-hop combination).
    """
    n = len(expected_rules)
    if n >= 3:
        return "3+"
    return str(n)


def army_retrieved(expected_army: str | None, retrieved: list[str]) -> bool | None:
    """Check whether the expected army id appears among retrieved nodes.

    Returns ``None`` when no army is expected.
    """
    if expected_army is None:
        return None
    return expected_army in set(retrieved)


def citation_coverage(expected: list[str], cited: list[str]) -> float | None:
    """Return the fraction of ``expected`` ids that were cited in the answer.

    This is citation *recall*: it rewards citing everything relevant but does
    not penalize citing irrelevant nodes too. See ``citation_precision`` for
    the complementary direction and ``citation_f1`` for the combination.

    Returns ``None`` when there are no expected rules to cite.
    """
    if not expected:
        return None
    cited_set = set(cited)
    hits = sum(1 for node_id in expected if node_id in cited_set)
    return hits / len(expected)


def citation_precision(expected: list[str], cited: list[str]) -> float | None:
    """Return the fraction of ``cited`` ids that are actually ``expected``.

    Without this, ``citation_coverage`` alone lets a model that cites every
    retrieved node score perfectly regardless of relevance — precision is
    what catches that failure mode. ``None`` when there is nothing expected
    (no ground truth to be right or wrong about) or nothing was cited
    (precision undefined, not zero).
    """
    if not expected or not cited:
        return None
    expected_set = set(expected)
    hits = sum(1 for node_id in cited if node_id in expected_set)
    return hits / len(cited)


def citation_f1(expected: list[str], cited: list[str]) -> float | None:
    """Harmonic mean of ``citation_precision`` and ``citation_coverage``."""
    return _f1(citation_precision(expected, cited), citation_coverage(expected, cited))


def build_retrieval_result(
    query_id: str,
    query: str,
    category: str,
    expected_rules: list[str],
    expected_army: str | None,
    retrieved: list[str],
    k: int | None = None,
) -> RetrievalResult:
    """Construct a ``RetrievalResult`` with recall, precision, and army flags computed."""
    return RetrievalResult(
        query_id=query_id,
        query=query,
        category=category,
        retrieved_ids=retrieved,
        expected_rules=expected_rules,
        expected_army=expected_army,
        recall_at_k=recall_at_k(expected_rules, retrieved, k),
        precision_at_k=precision_at_k(expected_rules, retrieved, k),
        f1_at_k=f1_at_k(expected_rules, retrieved, k),
        mrr=mrr(expected_rules, retrieved),
        ndcg_at_k=ndcg_at_k(expected_rules, retrieved, k),
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


def per_hop_metrics(
    results: list[RetrievalResult | AgentResult],
) -> dict[str, dict[str, float]]:
    """Mean recall/precision/F1 grouped by ``hop_bucket(expected_rules)``.

    This is the metric that most directly tests the thesis's central claim:
    whether a retrieval mode's advantage grows with reasoning-hop complexity,
    rather than a single overall mean (or the topical ``per_category_recall``)
    which conflates hop count with subject matter.
    """
    buckets: dict[str, dict[str, list[float]]] = {}
    for result in results:
        is_agent = isinstance(result, AgentResult)
        retrieval = result.retrieval if is_agent else result
        if not isinstance(retrieval, RetrievalResult):
            continue
        bucket = hop_bucket(retrieval.expected_rules)
        entry = buckets.setdefault(bucket, {"recall": [], "precision": [], "f1": []})
        if retrieval.recall_at_k is not None:
            entry["recall"].append(retrieval.recall_at_k)
        if retrieval.precision_at_k is not None:
            entry["precision"].append(retrieval.precision_at_k)
        if retrieval.f1_at_k is not None:
            entry["f1"].append(retrieval.f1_at_k)

    output: dict[str, dict[str, float]] = {}
    for bucket, metric_values in sorted(buckets.items()):
        means = {name: sum(vals) / len(vals) for name, vals in metric_values.items() if vals}
        if means:
            output[bucket] = means
    return output


def paired_significance(deltas: list[float]) -> dict[str, float | int]:
    """Wilcoxon signed-rank test on paired per-query metric deltas.

    ``deltas[i]`` is ``metric(mode_b, query_i) - metric(mode_a, query_i)`` for
    the same golden-set query under two retrieval modes — a paired design,
    since both modes are evaluated on the identical query set (ADR-0008).
    Returns ``{"statistic", "p_value", "n"}``. Wilcoxon raises on an
    all-zero-difference sample (e.g. comparing a mode against itself), so that
    case is handled explicitly as "not significant" rather than propagating
    the exception.
    """
    n = len(deltas)
    if n == 0 or all(d == 0 for d in deltas):
        return {"statistic": 0.0, "p_value": 1.0, "n": n}

    from scipy import stats

    statistic, p_value = stats.wilcoxon(deltas)
    return {"statistic": float(statistic), "p_value": float(p_value), "n": n}


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
    precision_values: list[float] = []
    f1_values: list[float] = []
    mrr_values: list[float] = []
    ndcg_values: list[float] = []
    correctness: list[float] = []
    groundedness: list[float] = []
    citation: list[float] = []
    citation_precision_values: list[float] = []
    citation_f1_values: list[float] = []
    hit_values: list[float] = []
    below: list[str] = []

    for result in results:
        is_agent = isinstance(result, AgentResult)
        retrieval = result.retrieval if is_agent else result
        verdict = result.verdict if is_agent else None

        if isinstance(retrieval, RetrievalResult):
            if retrieval.recall_at_k is not None:
                recall_values.append(retrieval.recall_at_k)
                if retrieval.recall_at_k < recall_threshold:
                    below.append(result.query_id)
            if retrieval.precision_at_k is not None:
                precision_values.append(retrieval.precision_at_k)
            if retrieval.f1_at_k is not None:
                f1_values.append(retrieval.f1_at_k)
            if retrieval.mrr is not None:
                mrr_values.append(retrieval.mrr)
            if retrieval.ndcg_at_k is not None:
                ndcg_values.append(retrieval.ndcg_at_k)

        if verdict is not None:
            correctness.append(verdict.correctness)
            groundedness.append(verdict.groundedness)
            citation.append(verdict.citation)
            mean_judge = (verdict.correctness + verdict.groundedness + verdict.citation) / 3
            if mean_judge < judge_threshold:
                below.append(result.query_id)

        if is_agent:
            if result.citation_precision is not None:
                citation_precision_values.append(result.citation_precision)
            if result.citation_f1 is not None:
                citation_f1_values.append(result.citation_f1)
            if result.answer_hit is not None:
                hit_values.append(1.0 if result.answer_hit else 0.0)

    def _mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    return SummaryMetrics(
        total_queries=len(results),
        recall_queries=len(recall_values),
        mean_recall_at_k=_mean(recall_values),
        mean_precision_at_k=_mean(precision_values),
        mean_f1_at_k=_mean(f1_values),
        mean_mrr=_mean(mrr_values),
        mean_ndcg_at_k=_mean(ndcg_values),
        mean_correctness=_mean(correctness),
        mean_groundedness=_mean(groundedness),
        mean_citation=_mean(citation),
        mean_citation_precision=_mean(citation_precision_values),
        mean_citation_f1=_mean(citation_f1_values),
        answer_hit_rate=_mean(hit_values),
        below_threshold=sorted(set(below)),
        per_category_recall=per_category_recall(results),
        per_hop_metrics=per_hop_metrics(results),
    )
