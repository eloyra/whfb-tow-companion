"""Semantic retrieval against the Neo4j vector indexes.

The retriever embeds the user query with the same SentenceTransformer model used at
ingestion time and runs label-scoped approximate-nearest-neighbour (ANN) searches
across all embeddable node labels. Results are merged globally by score and
deduplicated by node id.

ADR-0001 mandates ``neo4j-graphrag``'s ``VectorCypherRetriever`` for retrieval.
This implementation uses raw ``db.index.vector.queryNodes`` calls instead: they
expose the same HNSW ANN behaviour with less wrapper overhead, which keeps the
baseline small and easy to debug. A future refactor can wrap this in
``VectorCypherRetriever`` without changing the public ``retrieve()`` contract.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import neo4j
import numpy as np

from pipeline.constants import EMBEDDABLE_LABELS

logger = logging.getLogger(__name__)


def _label_to_snake(label: str) -> str:
    """Convert CamelCase label to snake_case for vector-index naming."""
    s = re.sub(r"([A-Z])", r"_\1", label).lower().lstrip("_")
    return s


class GraphRAGRetriever:
    """Embed a query and retrieve the most relevant nodes from Neo4j."""

    def __init__(
        self,
        driver: neo4j.Driver,
        embedder: Any,
        *,
        top_k: int = 8,
        per_label_k: int | None = None,
    ) -> None:
        self.driver = driver
        self.embedder = embedder
        self.top_k = top_k
        # Fetch a wider per-label candidate pool than top_k before the global
        # merge/cut: relevant nodes often rank outside the top-k within their
        # own label (e.g. a short CoreRule definition losing raw cosine score
        # to longer, more verbose FAQ/Lore text) but still belong in the
        # global top_k once all labels are pooled together.
        self.per_label_k = per_label_k or max(top_k * 3, 20)

    def retrieve(self, query: str) -> list[dict[str, Any]]:
        """Return the top-k most relevant nodes for ``query``.

        Each result is a dict with keys: ``id``, ``label``, ``name``, ``text``,
        ``url``, ``score``.
        """
        vector = self._embed(query)
        all_results: list[dict[str, Any]] = []

        for label in EMBEDDABLE_LABELS:
            try:
                label_results = self._query_label(label, vector, self.per_label_k)
            except Exception as exc:  # noqa: BLE001 — log and continue with other labels
                logger.warning("Vector query failed for %s: %s", label, exc)
                continue
            all_results.extend(label_results)

        # Deduplicate by id, keeping the highest score.
        by_id: dict[str, dict[str, Any]] = {}
        for result in all_results:
            rid = result["id"]
            if rid not in by_id or result["score"] > by_id[rid]["score"]:
                by_id[rid] = result

        ranked = sorted(by_id.values(), key=lambda r: r["score"], reverse=True)
        return ranked[: self.top_k]

    def _embed(self, query: str) -> list[float]:
        """Encode ``query`` into the embedding vector used by Neo4j."""
        vector = self.embedder.encode(query, convert_to_numpy=True, normalize_embeddings=False)
        if isinstance(vector, np.ndarray):
            vector = vector.tolist()
        # encode() may return a 2-D array if given a list; a single string should be 1-D.
        if isinstance(vector, list) and vector and isinstance(vector[0], list):
            vector = vector[0]
        return vector  # type: ignore[return-value]

    def _query_label(
        self,
        label: str,
        vector: list[float],
        k: int,
    ) -> list[dict[str, Any]]:
        """Run vector ANN for a single label."""
        index_name = f"{_label_to_snake(label)}_embedding_idx"
        cypher = """
            CALL db.index.vector.queryNodes($index_name, $k, $vector)
            YIELD node, score
            RETURN node.id AS id,
                   $label AS label,
                   node.name AS name,
                   coalesce(node.text, node.name, '') AS text,
                   node.url AS url,
                   score
            ORDER BY score DESC
        """
        with self.driver.session() as session:
            result = session.run(
                cypher,
                index_name=index_name,
                k=k,
                vector=vector,
                label=label,
            )
            rows = []
            for record in result:
                row = dict(record)
                # Cypher coalesce handles nulls; this also guards against missing props.
                row["text"] = row.get("text") or row.get("name") or ""
                rows.append(row)
            return rows
