"""
Entry point for the data pipeline.
Run individual stages or the full pipeline end to end.

Usage:
    python -m pipeline.run_pipeline --stage scrape
    python -m pipeline.run_pipeline --stage parse
    python -m pipeline.run_pipeline --stage graph
    python -m pipeline.run_pipeline --stage embed
    python -m pipeline.run_pipeline --stage translate
    python -m pipeline.run_pipeline --all
"""

import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

STAGES = ["scrape", "parse", "graph", "embed", "translate"]


def run_scrape() -> None:
    logger.info("Stage: scrape")
    # TODO: from pipeline.scraper.crawler import Crawler; Crawler().run()


def run_parse() -> None:
    logger.info("Stage: parse")
    # TODO: from pipeline.scraper.parsers import run_all_parsers; run_all_parsers()


def run_graph() -> None:
    logger.info("Stage: graph")
    # TODO: from pipeline.graph.builder import GraphBuilder; GraphBuilder().build()


def run_embed() -> None:
    logger.info("Stage: embed")
    # TODO: from pipeline.embeddings.generator import EmbeddingGenerator; EmbeddingGenerator().run()


def run_translate() -> None:
    logger.info("Stage: translate")
    # TODO: from pipeline.i18n.translator import Translator; Translator().run()


STAGE_FN = {
    "scrape":    run_scrape,
    "parse":     run_parse,
    "graph":     run_graph,
    "embed":     run_embed,
    "translate": run_translate,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Warhammer RAG data pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stage", choices=STAGES, help="Run a single pipeline stage")
    group.add_argument("--all", action="store_true", help="Run all stages in order")
    args = parser.parse_args()

    if args.all:
        for stage in STAGES:
            STAGE_FN[stage]()
    else:
        STAGE_FN[args.stage]()


if __name__ == "__main__":
    main()
