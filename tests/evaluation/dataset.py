"""Golden-set loading and validation helpers."""

from __future__ import annotations

import json
from pathlib import Path

from tests.evaluation.models import Query

DEFAULT_DATASET_PATH = Path(__file__).with_name("test_queries.json")


def load_queries(path: Path | None = None) -> list[Query]:
    """Load the golden query set from JSON and validate each record."""
    path = path or DEFAULT_DATASET_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected a JSON array in {path}")
    return [Query.model_validate(item) for item in raw]


def get_queries_by_category(queries: list[Query]) -> dict[str, list[Query]]:
    """Group queries by category for per-category reporting."""
    groups: dict[str, list[Query]] = {}
    for q in queries:
        groups.setdefault(q.category, []).append(q)
    return groups
