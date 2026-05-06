"""
Neo4j vector index management.

``create_vector_indexes(driver)`` creates one HNSW vector index per embeddable
label, named ``<snake_label>_embedding_idx``.  All indexes are created with
``IF NOT EXISTS`` so the function is idempotent.

Vector indexes must be created *after* at least one node with an ``embedding``
property exists — Neo4j ignores the property type hint until nodes are present.
This is why index creation is deferred to the end of the embedding stage rather
than included in the DDL stage.

Rationale for per-label indexes: Neo4j 5.x vector indexes are per-label-per-property,
and per-label scoping gives cheaper label-scoped ANN queries from
``VectorCypherRetriever`` (see ADR-0001, ADR-0005).
"""

from __future__ import annotations

import logging
import os

import neo4j
from dotenv import load_dotenv

from pipeline.constants import EMBEDDABLE_LABELS, EMBEDDING_DIM, VECTOR_INDEX_SIMILARITY

load_dotenv()

logger = logging.getLogger(__name__)


def _label_to_snake(label: str) -> str:
    """Convert CamelCase label to snake_case for index naming."""
    import re

    s = re.sub(r"([A-Z])", r"_\1", label).lower().lstrip("_")
    return s


def create_vector_indexes(
    driver: neo4j.Driver,
    dim: int | None = None,
    similarity: str | None = None,
) -> None:
    """Create one vector index per embeddable label, idempotent."""
    dim = dim or int(os.environ.get("EMBEDDING_DIM", EMBEDDING_DIM))
    similarity = similarity or os.environ.get("VECTOR_INDEX_SIMILARITY", VECTOR_INDEX_SIMILARITY)

    with driver.session() as session:
        for label in EMBEDDABLE_LABELS:
            index_name = f"{_label_to_snake(label)}_embedding_idx"
            cypher = f"""
                CREATE VECTOR INDEX {index_name} IF NOT EXISTS
                FOR (n:{label}) ON (n.embedding)
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {dim},
                        `vector.similarity_function`: '{similarity}'
                    }}
                }}
            """
            session.run(cypher)
            logger.info("Vector index ready: %s (%d-dim, %s)", index_name, dim, similarity)

    logger.info("All vector indexes created")
