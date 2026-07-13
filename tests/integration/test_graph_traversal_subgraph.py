"""Integration test for ``graph_traversal.subgraph()`` against a real Neo4j instance.

Requires Docker and testcontainers[neo4j]. The test is automatically skipped when
either dependency is missing, so it never blocks the CI unit-test suite.

Unlike the unit tests in ``tests/unit/test_graph_traversal.py`` (which fake the
driver entirely), this exercises the real ``apoc.path.subgraphAll`` procedure —
APOC procedure names and signatures have drifted across versions, so a real-DB
smoke test is the only way to catch that class of bug.

Run manually:
    pip install testcontainers[neo4j]
    pytest tests/integration/test_graph_traversal_subgraph.py -v
"""

from __future__ import annotations

import pytest

try:
    from testcontainers.neo4j import Neo4jContainer

    _HAS_TESTCONTAINERS = True
except ImportError:
    _HAS_TESTCONTAINERS = False

pytestmark = pytest.mark.skipif(
    not _HAS_TESTCONTAINERS,
    reason="testcontainers[neo4j] not installed",
)

# ---------------------------------------------------------------------------
# Tiny synthetic graph:
#
#   ghoul-king --HAS_RULE--> fear --REFERENCES--> terror
#
# "fear" is the center: depth=2 should reach both "ghoul-king" (1 hop, via an
# incoming edge — subgraphAll traverses both directions by default) and
# "terror" (1 hop, outgoing).
# ---------------------------------------------------------------------------

_SEED_CYPHER = """
    CREATE (fear:SpecialRule {id: 'fear', name: 'Fear', url: 'https://example.com/fear'})
    CREATE (terror:SpecialRule {id: 'terror', name: 'Terror', url: 'https://example.com/terror'})
    CREATE (ghoul:Unit {id: 'ghoul-king', name: 'Ghoul King', url: 'https://example.com/ghoul-king'})
    CREATE (fear)-[:REFERENCES]->(terror)
    CREATE (ghoul)-[:HAS_RULE]->(fear)
"""


@pytest.fixture(scope="module")
def neo4j_container():
    with Neo4jContainer("neo4j:5.24-community").with_env("NEO4J_PLUGINS", '["apoc"]') as container:
        yield container


@pytest.fixture(scope="module")
def driver(neo4j_container):
    import neo4j as neo4j_driver

    bolt_url = neo4j_container.get_connection_url()
    d = neo4j_driver.GraphDatabase.driver(
        bolt_url, auth=("neo4j", neo4j_container.password)
    )
    with d.session() as session:
        session.run(_SEED_CYPHER)
    yield d
    d.close()


class TestSubgraphIntegration:
    def test_apoc_subgraph_all_runs_and_returns_expected_neighborhood(self, driver) -> None:
        from backend.rag.graph_traversal import subgraph

        result = subgraph(driver, "fear", depth=2)

        node_ids = {n["id"] for n in result["nodes"]}
        assert node_ids == {"fear", "terror", "ghoul-king"}

        edge_pairs = {(e["source"], e["target"], e["rel_type"]) for e in result["edges"]}
        assert edge_pairs == {
            ("fear", "terror", "REFERENCES"),
            ("ghoul-king", "fear", "HAS_RULE"),
        }

    def test_apoc_subgraph_all_respects_depth_limit(self, driver) -> None:
        from backend.rag.graph_traversal import subgraph

        # depth=1 from "terror" should reach only "fear" (1 hop), not
        # "ghoul-king" (2 hops away via fear).
        result = subgraph(driver, "terror", depth=1)

        node_ids = {n["id"] for n in result["nodes"]}
        assert node_ids == {"terror", "fear"}
        assert "ghoul-king" not in node_ids

    def test_node_properties_never_include_embedding(self, driver) -> None:
        from backend.rag.graph_traversal import subgraph

        result = subgraph(driver, "fear", depth=1)

        for node in result["nodes"]:
            assert "embedding" not in node
            assert set(node.keys()) == {"id", "label", "name", "source_url"}

    def test_subgraph_not_found_returns_empty_against_real_db(self, driver) -> None:
        from backend.rag.graph_traversal import subgraph

        assert subgraph(driver, "does-not-exist", depth=2) == {"nodes": [], "edges": []}
