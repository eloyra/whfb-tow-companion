"""
Neo4j schema DDL: uniqueness constraints and btree indexes.

``apply_constraints_and_indexes(driver)`` is idempotent — every statement uses
``IF NOT EXISTS`` so it is safe to call on every graph build.

Vector indexes are NOT created here; they live in ``pipeline.embeddings.vector_store``
and are created after node embeddings exist (Neo4j requires at least one node with
the embedding property before an index is useful).
"""

from __future__ import annotations

import logging

import neo4j

from pipeline.constants import EMBEDDABLE_LABELS

logger = logging.getLogger(__name__)

# Name of the single multi-label full-text index used by the "hybrid"
# retrieval mode (see ADR-0008, backend/rag/retriever.py::_query_fulltext).
FULLTEXT_INDEX_NAME = "archive_fulltext_idx"

# ---------------------------------------------------------------------------
# Uniqueness constraints (one per label)
# ---------------------------------------------------------------------------

_CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT army_id        IF NOT EXISTS FOR (n:Army)        REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT unit_id        IF NOT EXISTS FOR (n:Unit)        REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT profile_id     IF NOT EXISTS FOR (n:Profile)     REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT special_rule_id IF NOT EXISTS FOR (n:SpecialRule) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT corerule_id    IF NOT EXISTS FOR (n:CoreRule)    REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT document_id    IF NOT EXISTS FOR (n:Document)    REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT trooptype_id   IF NOT EXISTS FOR (n:TroopType)   REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT terrain_id     IF NOT EXISTS FOR (n:Terrain)     REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT lore_id        IF NOT EXISTS FOR (n:Lore)        REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT spell_id       IF NOT EXISTS FOR (n:Spell)       REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT weapon_id      IF NOT EXISTS FOR (n:Weapon)      REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT magicitem_id   IF NOT EXISTS FOR (n:MagicItem)   REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT upgrade_id     IF NOT EXISTS FOR (n:Upgrade)     REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT complist_id    IF NOT EXISTS FOR (n:CompositionList)"
    "  REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT compslot_id    IF NOT EXISTS FOR (n:CompositionSlot)"
    "  REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT faq_id         IF NOT EXISTS FOR (n:FAQ)         REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT errata_id      IF NOT EXISTS FOR (n:Errata)      REQUIRE n.id IS UNIQUE",
]

# ---------------------------------------------------------------------------
# Btree indexes (frequently filtered / sorted properties)
# ---------------------------------------------------------------------------

_INDEXES: list[str] = [
    "CREATE INDEX unit_url        IF NOT EXISTS FOR (n:Unit)        ON (n.url)",
    "CREATE INDEX special_rule_url IF NOT EXISTS FOR (n:SpecialRule) ON (n.url)",
    "CREATE INDEX spell_url       IF NOT EXISTS FOR (n:Spell)        ON (n.url)",
    "CREATE INDEX terrain_class   IF NOT EXISTS FOR (n:Terrain)      ON (n.terrain_class)",
    "CREATE INDEX unit_troop_type IF NOT EXISTS FOR (n:Unit)         ON (n.troop_type_id)",
    "CREATE INDEX corerule_url    IF NOT EXISTS FOR (n:CoreRule)     ON (n.url)",
    "CREATE INDEX document_url    IF NOT EXISTS FOR (n:Document)     ON (n.url)",
    # Profile-specific: querying by stat values or sub-profile name
    "CREATE INDEX profile_order   IF NOT EXISTS FOR (n:Profile)      ON (n.order)",
    "CREATE INDEX profile_name    IF NOT EXISTS FOR (n:Profile)      ON (n.name)",
    # Upgrade-specific: frequent filters in RAG queries
    "CREATE INDEX upgrade_type         IF NOT EXISTS FOR (n:Upgrade) ON (n.upgrade_type)",
    "CREATE INDEX upgrade_profile      IF NOT EXISTS FOR (n:Upgrade) ON (n.applies_to_profile)",
    "CREATE INDEX upgrade_mutex        IF NOT EXISTS FOR (n:Upgrade) ON (n.mutex_group)",
]


def _fulltext_index_statement() -> str:
    """Build the ``CREATE FULLTEXT INDEX`` statement over every embeddable label.

    Unlike vector indexes (which require at least one populated node before
    Neo4j accepts the type hint — see ``pipeline/embeddings/vector_store.py``),
    full-text indexes have no such requirement, so this one lives in DDL
    alongside the constraints/btree indexes rather than in the embeddings
    stage. It is a single index spanning all labels (rather than one per
    label like the vector indexes) because full-text search benefits from one
    globally-ranked BM25 result list — see ADR-0008.
    """
    label_pattern = "|".join(EMBEDDABLE_LABELS)
    return (
        f"CREATE FULLTEXT INDEX {FULLTEXT_INDEX_NAME} IF NOT EXISTS "
        f"FOR (n:{label_pattern}) ON EACH [n.name, n.text]"
    )


def apply_constraints_and_indexes(driver: neo4j.Driver) -> None:
    """Create all constraints and indexes idempotently."""
    statements = [*_CONSTRAINTS, *_INDEXES, _fulltext_index_statement()]
    logger.info("Applying %d DDL statements (IF NOT EXISTS)", len(statements))
    with driver.session() as session:
        for stmt in statements:
            session.run(stmt)
    logger.info("DDL complete")
