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
    SummaryMetrics,
)
from tests.evaluation.runner import run_full_evaluation, run_retrieval_evaluation
from tests.evaluation.scoring import aggregate_metrics

REPORTS_DIR = Path(__file__).with_name("reports")

# Retrieval modes compared by --compare; order is preserved in report tables.
# See ADR-0008 for mode semantics.
RAG_MODES = ("vector", "graph", "hybrid")


def _fmt_float(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "n/a"


def _render_markdown(report: EvaluationReport) -> str:
    lines: list[str] = []
    lines.append("# RAG Evaluation Report")
    lines.append(f"\n- **Mode:** {report.mode}")
    lines.append(f"- **Queries:** {report.total_queries}")
    lines.append(f"- **Generated:** {datetime.now(timezone.utc).isoformat()}\n")

    metrics = report.metrics
    lines.append("## Aggregate metrics\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(
        f"| Mean recall@{report.config.get('top_k', 8)} | {_fmt_float(metrics.mean_recall_at_k)} |"
    )
    lines.append(f"| Mean correctness | {_fmt_float(metrics.mean_correctness)} |")
    lines.append(f"| Mean groundedness | {_fmt_float(metrics.mean_groundedness)} |")
    lines.append(f"| Mean citation | {_fmt_float(metrics.mean_citation)} |")
    lines.append(f"| Below threshold | {len(metrics.below_threshold)} |\n")

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
    lines.append("## Aggregate metrics\n")
    lines.append("| Metric | " + " | ".join(report.modes) + " |")
    lines.append("|---|" + "---|" * len(report.modes))
    lines.append(
        f"| Mean recall@{top_k} | "
        + " | ".join(_fmt_float(report.per_mode[m].mean_recall_at_k) for m in report.modes)
        + " |"
    )
    lines.append(
        "| Mean correctness | "
        + " | ".join(_fmt_float(report.per_mode[m].mean_correctness) for m in report.modes)
        + " |"
    )
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
        for rag_mode in RAG_MODES:
            print(f"Running mode={rag_mode}...")
            _results, metrics = await _run_one_mode(queries, args, rag_mode)
            per_mode_metrics[rag_mode] = metrics
            print(f"  Mean recall@{args.top_k}: {_fmt_float(metrics.mean_recall_at_k)}")

        comparison = ComparisonReport(
            modes=list(RAG_MODES),
            total_queries=len(queries),
            per_mode=per_mode_metrics,
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
