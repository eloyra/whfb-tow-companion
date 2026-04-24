"""
Embedding generator for the Neo4j knowledge graph.

``EmbeddingGenerator().run()`` iterates over every embeddable label, fetches
nodes whose ``embedding`` property is NULL (resumable — re-running skips
already-embedded nodes), builds dense graph-context text via ``text.py``,
calls the SentenceTransformer model, and writes vectors back to Neo4j.

After all labels are processed, vector indexes are created via ``vector_store.py``.
"""

from __future__ import annotations

import logging
import os

import numpy as np
from dotenv import load_dotenv
from tqdm import tqdm

from pipeline.constants import EMBEDDABLE_LABELS
from pipeline.embeddings import text as text_builder
from pipeline.embeddings import vector_store
from pipeline.graph import client

load_dotenv()

logger = logging.getLogger(__name__)

_DEFAULT_BATCH = 64
_WRITE_BATCH = 200


class EmbeddingGenerator:
    """Orchestrates embedding generation for all embeddable graph labels."""

    def run(self) -> None:
        model_name = os.environ.get("EMBEDDING_MODEL", "paraphrase-multilingual-mpnet-base-v2")
        device = os.environ.get("EMBEDDING_DEVICE", "cpu")
        batch_size = int(os.environ.get("EMBEDDING_BATCH_SIZE", _DEFAULT_BATCH))

        logger.info("Loading embedding model: %s (device=%s)", model_name, device)
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name, device=device)

        driver = client.get_driver()

        for label in EMBEDDABLE_LABELS:
            self._embed_label(driver, model, label, batch_size)

        logger.info("Creating vector indexes")
        vector_store.create_vector_indexes(driver)
        logger.info("Embedding stage complete")

    # ------------------------------------------------------------------
    # Per-label embedding
    # ------------------------------------------------------------------

    def _embed_label(self, driver, model, label: str, batch_size: int) -> None:
        ids = self._fetch_unembedded_ids(driver, label)
        if not ids:
            logger.info("%s: all nodes already embedded, skipping", label)
            return

        logger.info("%s: embedding %d nodes", label, len(ids))
        total_written = 0

        for chunk_start in tqdm(
            range(0, len(ids), batch_size),
            desc=f"Embedding {label}",
            unit="batch",
        ):
            batch_ids = ids[chunk_start : chunk_start + batch_size]

            texts = text_builder.build_for_label(driver, label, batch_ids)

            # Pair (id, text), skip empty
            pairs = [(nid, t) for nid, t in zip(batch_ids, texts) if t.strip()]
            if not pairs:
                continue

            embed_ids, embed_texts = zip(*pairs)
            vectors: np.ndarray = model.encode(
                list(embed_texts),
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=False,
            )

            self._write_embeddings(driver, label, list(embed_ids), vectors)
            total_written += len(embed_ids)

        logger.info("%s: wrote %d embeddings", label, total_written)

    def _fetch_unembedded_ids(self, driver, label: str) -> list[str]:
        query = f"MATCH (n:{label}) WHERE n.embedding IS NULL RETURN n.id AS nid"
        with driver.session() as session:
            result = session.run(query)
            return [rec["nid"] for rec in result if rec["nid"]]

    def _write_embeddings(
        self, driver, label: str, ids: list[str], vectors: np.ndarray
    ) -> None:
        rows = [
            {"id": nid, "embedding": vectors[i].tolist()}
            for i, nid in enumerate(ids)
        ]
        query = f"""
            UNWIND $rows AS row
            MATCH (n:{label} {{id: row.id}})
            SET n.embedding = row.embedding
        """
        for start in range(0, len(rows), _WRITE_BATCH):
            batch = rows[start : start + _WRITE_BATCH]
            with driver.session() as session:
                session.execute_write(lambda tx, b=batch: tx.run(query, rows=b))
