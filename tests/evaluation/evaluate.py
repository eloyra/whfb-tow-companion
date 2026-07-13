"""CLI entry point for the RAG evaluation harness.

Usage:
    uv run python -m tests.evaluation.evaluate
    uv run python -m tests.evaluation.evaluate --full --judge-model claude-haiku-4-5
    uv run python -m tests.evaluation.evaluate --top-k 10 --output-dir reports/
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.api.dependencies import get_llm
from tests.evaluation.dataset import load_queries
from tests.evaluation.models import (
    AgentResult,
    ComparisonReport,
    EvaluationReport,
    Query,
    RetrievalResult,
    SignificanceResult,
    SummaryMetrics,
)
from tests.evaluation.runner import run_full_evaluation, run_retrieval_evaluation
from tests.evaluation.scoring import aggregate_metrics, paired_significance

REPORTS_DIR = Path(__file__).with_name("reports")

# Retrieval modes compared by --compare; order is preserved in report tables.
# See ADR-0008 for mode semantics.
RAG_MODES = ("vector", "graph", "hybrid")


def _fmt_float(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "n/a"


def _hop_sort_key(bucket: str) -> tuple[int, int | str]:
    """Sort hop buckets numerically ("0" < "1" < "2" < "3+") not lexically."""
    return (0, int(bucket)) if bucket.isdigit() else (1, bucket)


def _render_markdown(report: EvaluationReport) -> str:
    lines: list[str] = []
    lines.append("# RAG Evaluation Report")
    lines.append(f"\n- **Mode:** {report.mode}")
    lines.append(f"- **Queries:** {report.total_queries}")
    lines.append(f"- **Generated:** {datetime.now(timezone.utc).isoformat()}\n")

    metrics = report.metrics
    top_k = report.config.get("top_k", 8)
    lines.append("## Aggregate metrics\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Mean recall@{top_k} | {_fmt_float(metrics.mean_recall_at_k)} |")
    lines.append(f"| Mean precision@{top_k} | {_fmt_float(metrics.mean_precision_at_k)} |")
    lines.append(f"| Mean F1@{top_k} | {_fmt_float(metrics.mean_f1_at_k)} |")
    lines.append(f"| Mean MRR | {_fmt_float(metrics.mean_mrr)} |")
    lines.append(f"| Mean nDCG@{top_k} | {_fmt_float(metrics.mean_ndcg_at_k)} |")
    lines.append(f"| Mean correctness | {_fmt_float(metrics.mean_correctness)} |")
    lines.append(f"| Mean groundedness | {_fmt_float(metrics.mean_groundedness)} |")
    lines.append(f"| Mean citation (recall) | {_fmt_float(metrics.mean_citation)} |")
    lines.append(f"| Mean citation precision | {_fmt_float(metrics.mean_citation_precision)} |")
    lines.append(f"| Mean citation F1 | {_fmt_float(metrics.mean_citation_f1)} |")
    lines.append(f"| Answer hit rate | {_fmt_float(metrics.answer_hit_rate)} |")
    lines.append(f"| Below threshold | {len(metrics.below_threshold)} |\n")

    if metrics.per_hop_metrics:
        lines.append("## Per-hop-count metrics (reasoning complexity proxy)\n")
        lines.append("| Hop bucket | Recall | Precision | F1 |")
        lines.append("|---|---|---|---|")
        for bucket, vals in sorted(
            metrics.per_hop_metrics.items(), key=lambda kv: _hop_sort_key(kv[0])
        ):
            lines.append(
                f"| {bucket} | {_fmt_float(vals.get('recall'))} | "
                f"{_fmt_float(vals.get('precision'))} | {_fmt_float(vals.get('f1'))} |"
            )
        lines.append("")

    if metrics.below_threshold:
        lines.append("## Queries below threshold\n")
        for query_id in metrics.below_threshold:
            lines.append(f"- {query_id}")
        lines.append("")

    lines.append("## Per-query results\n")
    lines.append("| ID | Category | Recall | Judge (c/g/ci) |")
    lines.append("|---|---|---|---|")
    for result in report.results:
        recall = _fmt_float(result.recall_at_k) if hasattr(result, "recall_at_k") else "n/a"
        if hasattr(result, "verdict") and result.verdict:
            v = result.verdict
            judge = f"{v.correctness}/{v.groundedness}/{v.citation}"
        else:
            judge = "n/a"
        lines.append(f"| {result.query_id} | {result.category} | {recall} | {judge} |")
    lines.append("")
    return "\n".join(lines)


def _write_reports(report: EvaluationReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"eval_{timestamp}.json"
    md_path = output_dir / f"eval_{timestamp}.md"
    json_path.write_text(
        report.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, md_path


def _render_comparison_markdown(report: ComparisonReport) -> str:
    """Render a side-by-side comparison of retrieval modes (ADR-0008)."""
    lines: list[str] = []
    lines.append("# RAG Retrieval-Mode Comparison Report")
    lines.append(f"\n- **Queries:** {report.total_queries}")
    lines.append(f"- **Modes:** {', '.join(report.modes)}")
    lines.append(f"- **Generated:** {datetime.now(timezone.utc).isoformat()}\n")

    top_k = report.config.get("top_k", 8)

    def _row(label: str, getter) -> str:
        values = " | ".join(_fmt_float(getter(report.per_mode[m])) for m in report.modes)
        return f"| {label} | {values} |"

    lines.append("## Aggregate metrics\n")
    lines.append("| Metric | " + " | ".join(report.modes) + " |")
    lines.append("|---|" + "---|" * len(report.modes))
    lines.append(_row(f"Mean recall@{top_k}", lambda sm: sm.mean_recall_at_k))
    lines.append(_row(f"Mean precision@{top_k}", lambda sm: sm.mean_precision_at_k))
    lines.append(_row(f"Mean F1@{top_k}", lambda sm: sm.mean_f1_at_k))
    lines.append(_row("Mean MRR", lambda sm: sm.mean_mrr))
    lines.append(_row(f"Mean nDCG@{top_k}", lambda sm: sm.mean_ndcg_at_k))
    lines.append(_row("Mean correctness", lambda sm: sm.mean_correctness))
    lines.append(_row("Mean citation (recall)", lambda sm: sm.mean_citation))
    lines.append(_row("Mean citation precision", lambda sm: sm.mean_citation_precision))
    lines.append(_row("Mean citation F1", lambda sm: sm.mean_citation_f1))
    lines.append(_row("Answer hit rate", lambda sm: sm.answer_hit_rate))
    lines.append(
        "| Below threshold | "
        + " | ".join(str(len(report.per_mode[m].below_threshold)) for m in report.modes)
        + " |\n"
    )

    categories = sorted(
        {cat for m in report.modes for cat in report.per_mode[m].per_category_recall}
    )
    if categories:
        lines.append("## Per-category recall\n")
        lines.append("| Category | " + " | ".join(report.modes) + " |")
        lines.append("|---|" + "---|" * len(report.modes))
        for cat in categories:
            row = " | ".join(
                _fmt_float(report.per_mode[m].per_category_recall.get(cat)) for m in report.modes
            )
            lines.append(f"| {cat} | {row} |")
        lines.append("")

    hop_buckets = sorted(
        {bucket for m in report.modes for bucket in report.per_mode[m].per_hop_metrics},
        key=_hop_sort_key,
    )
    if hop_buckets:
        lines.append(
            "## Per-hop-count metrics (reasoning complexity proxy — "
            "does the advantage grow with hop count?)\n"
        )
        for metric_key, label in (("recall", "Recall"), ("precision", "Precision"), ("f1", "F1")):
            lines.append(f"### {label}\n")
            lines.append("| Hop bucket | " + " | ".join(report.modes) + " |")
            lines.append("|---|" + "---|" * len(report.modes))
            for bucket in hop_buckets:
                row = " | ".join(
                    _fmt_float(report.per_mode[m].per_hop_metrics.get(bucket, {}).get(metric_key))
                    for m in report.modes
                )
                lines.append(f"| {bucket} | {row} |")
            lines.append("")

    if report.significance:
        lines.append("## Statistical significance (paired Wilcoxon signed-rank)\n")
        lines.append("| Baseline | Mode | Metric | n | p-value | Significant (α=0.05) |")
        lines.append("|---|---|---|---|---|---|")
        for sig in report.significance:
            lines.append(
                f"| {sig.mode_a} | {sig.mode_b} | {sig.metric} | {sig.n} | "
                f"{sig.p_value:.4f} | {'Yes' if sig.significant else 'No'} |"
            )
        lines.append("")

    return "\n".join(lines)


def _write_comparison_reports(report: ComparisonReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"compare_{timestamp}.json"
    md_path = output_dir / f"compare_{timestamp}.md"
    json_path.write_text(
        report.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )
    md_path.write_text(_render_comparison_markdown(report), encoding="utf-8")
    return json_path, md_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate the GraphRAG pipeline against the golden set."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run the full agent and optional LLM-judge instead of retrieval-only.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=8,
        help="Number of seed nodes to retrieve per query (default: 8).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPORTS_DIR,
        help="Directory for JSON + Markdown report files.",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Optional judge model name; overrides the model from get_llm().",
    )
    parser.add_argument(
        "--recall-threshold",
        type=float,
        default=0.5,
        help="Recall@k threshold below which a query is flagged (default: 0.5).",
    )
    parser.add_argument(
        "--judge-threshold",
        type=float,
        default=1.0,
        help="Mean judge-score threshold below which a query is flagged (default: 1.0).",
    )
    parser.add_argument(
        "--mode",
        choices=RAG_MODES,
        default=None,
        help="Retrieval mode override (default: RAG_MODE env var, or 'graph'). See ADR-0008.",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run all retrieval modes (vector/graph/hybrid) and emit a comparison report "
        "instead of a single-mode report. Ignores --mode.",
    )
    return parser


def _per_query_metric(
    results: list[RetrievalResult] | list[AgentResult],
    metric: str,
) -> dict[str, float]:
    """Extract a single per-query metric value, keyed by ``query_id``.

    ``metric="answer_hit"`` reads the agent-only binary hit flag; any other
    name is read off the (possibly nested) ``RetrievalResult``. Skips queries
    where the metric is ``None`` (not applicable, e.g. open-ended queries).
    """
    values: dict[str, float] = {}
    for result in results:
        is_agent = isinstance(result, AgentResult)
        if metric == "answer_hit":
            if is_agent and result.answer_hit is not None:
                values[result.query_id] = 1.0 if result.answer_hit else 0.0
            continue
        retrieval = result.retrieval if is_agent else result
        if isinstance(retrieval, RetrievalResult):
            value = getattr(retrieval, metric, None)
            if value is not None:
                values[result.query_id] = value
    return values


def _pairwise_significance(
    per_mode_results: dict[str, list[RetrievalResult] | list[AgentResult]],
    metric: str,
    baseline: str = "vector",
) -> list[SignificanceResult]:
    """Paired Wilcoxon test of ``baseline`` vs. every other mode on ``metric``.

    Paired because every mode runs against the identical golden-set queries
    (ADR-0008) — the comparison is baseline-vs-mode on the same query, not two
    independent samples.
    """
    baseline_values = _per_query_metric(per_mode_results[baseline], metric)
    significance: list[SignificanceResult] = []
    for mode, results in per_mode_results.items():
        if mode == baseline:
            continue
        other_values = _per_query_metric(results, metric)
        shared_ids = sorted(set(baseline_values) & set(other_values))
        deltas = [other_values[qid] - baseline_values[qid] for qid in shared_ids]
        outcome = paired_significance(deltas)
        significance.append(
            SignificanceResult(
                mode_a=baseline,
                mode_b=mode,
                metric=metric,
                statistic=outcome["statistic"],
                p_value=outcome["p_value"],
                n=outcome["n"],
                significant=outcome["p_value"] < 0.05,
            )
        )
    return significance


async def _run_one_mode(
    queries: list[Query],
    args: argparse.Namespace,
    rag_mode: str,
) -> tuple[list[RetrievalResult] | list[AgentResult], SummaryMetrics]:
    """Run retrieval-only or full-agent evaluation for a single ``rag_mode``."""
    if args.full:
        judge_llm = get_llm()
        if args.judge_model:
            judge_llm = judge_llm.bind(model=args.judge_model)
        results = await run_full_evaluation(
            queries,
            top_k=args.top_k,
            judge_llm=judge_llm,
            mode=rag_mode,
        )
    else:
        results = run_retrieval_evaluation(queries, top_k=args.top_k, mode=rag_mode)

    metrics = aggregate_metrics(
        results,
        recall_threshold=args.recall_threshold,
        judge_threshold=args.judge_threshold,
    )
    return results, metrics


async def _main_async(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    queries = load_queries()
    print(f"Loaded {len(queries)} golden queries")

    if args.compare:
        per_mode_metrics: dict[str, SummaryMetrics] = {}
        per_mode_results: dict[str, list[RetrievalResult] | list[AgentResult]] = {}
        for rag_mode in RAG_MODES:
            print(f"Running mode={rag_mode}...")
            results, metrics = await _run_one_mode(queries, args, rag_mode)
            per_mode_results[rag_mode] = results
            per_mode_metrics[rag_mode] = metrics
            print(f"  Mean recall@{args.top_k}: {_fmt_float(metrics.mean_recall_at_k)}")

        # Full-agent mode: the answer's correctness is the metric that
        # actually matters end-to-end. Retrieval-only mode has no answer, so
        # fall back to recall@k, the harness's existing headline metric.
        significance_metric = "answer_hit" if args.full else "recall_at_k"
        significance = _pairwise_significance(per_mode_results, significance_metric)

        comparison = ComparisonReport(
            modes=list(RAG_MODES),
            total_queries=len(queries),
            per_mode=per_mode_metrics,
            significance=significance,
            config={
                "top_k": args.top_k,
                "recall_threshold": args.recall_threshold,
                "judge_threshold": args.judge_threshold,
                "full": args.full,
            },
        )
        json_path, md_path = _write_comparison_reports(comparison, args.output_dir)
        print(f"Wrote JSON comparison: {json_path}")
        print(f"Wrote Markdown comparison: {md_path}")
        return 0 if all(not m.below_threshold for m in per_mode_metrics.values()) else 1

    rag_mode = args.mode or os.environ.get("RAG_MODE", "graph")
    results, metrics = await _run_one_mode(queries, args, rag_mode)
    report = EvaluationReport(
        mode="full" if args.full else "retrieval",
        total_queries=len(queries),
        metrics=metrics,
        results=results,
        config={
            "rag_mode": rag_mode,
            "top_k": args.top_k,
            "recall_threshold": args.recall_threshold,
            "judge_threshold": args.judge_threshold,
            "judge_model": args.judge_model or os.environ.get("LLM_MODEL", "default"),
        },
    )

    json_path, md_path = _write_reports(report, args.output_dir)
    print(f"Wrote JSON report: {json_path}")
    print(f"Wrote Markdown report: {md_path}")
    print(f"Mean recall@{args.top_k}: {_fmt_float(metrics.mean_recall_at_k)}")
    if metrics.mean_correctness is not None:
        print(f"Mean judge correctness: {_fmt_float(metrics.mean_correctness)}")
    if metrics.below_threshold:
        print(f"Queries below threshold: {', '.join(metrics.below_threshold)}")
    return 0 if not metrics.below_threshold else 1


def main(argv: list[str] | None = None) -> int:
    """Synchronous wrapper around the async evaluation entry point."""
    return asyncio.run(_main_async(argv))


if __name__ == "__main__":
    sys.exit(main())
