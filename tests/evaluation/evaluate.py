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
from tests.evaluation.models import EvaluationReport
from tests.evaluation.runner import run_full_evaluation, run_retrieval_evaluation
from tests.evaluation.scoring import aggregate_metrics

REPORTS_DIR = Path(__file__).with_name("reports")


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
    return parser


async def _main_async(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    queries = load_queries()
    print(f"Loaded {len(queries)} golden queries")

    if args.full:
        judge_llm = None
        if args.judge_model:
            judge_llm = get_llm().bind(model=args.judge_model)
        results = await run_full_evaluation(
            queries,
            top_k=args.top_k,
            judge_llm=judge_llm,
        )
        mode = "full"
    else:
        results = run_retrieval_evaluation(queries, top_k=args.top_k)
        mode = "retrieval"

    metrics = aggregate_metrics(
        results,
        recall_threshold=args.recall_threshold,
        judge_threshold=args.judge_threshold,
    )
    report = EvaluationReport(
        mode=mode,
        total_queries=len(queries),
        metrics=metrics,
        results=results,
        config={
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
