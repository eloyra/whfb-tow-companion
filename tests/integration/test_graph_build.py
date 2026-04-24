"""
Integration test for GraphBuilder + EmbeddingGenerator against a real Neo4j instance.

Requires Docker and testcontainers[neo4j].  The test is automatically skipped when
either dependency is missing, so it never blocks the CI unit-test suite.

Run manually:
    pip install testcontainers[neo4j]
    pytest tests/integration/test_graph_build.py -v
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

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
# Synthetic dataset helpers
# ---------------------------------------------------------------------------

_ARMY = {"node_type": "army", "id": "test-army", "name": "Test Army",
         "url": "https://example.com/army/test-army",
         "source_citation_book": "Test Book", "source_citation_page": 1}

_TROOP_TYPE = {"node_type": "troop_type", "id": "regular-infantry", "name": "Regular Infantry",
               "url": "https://example.com/troop-types/regular-infantry",
               "source_citation_book": "Core Rules", "source_citation_page": 5,
               "category": "Infantry", "min_models_for_rank_bonus": None,
               "max_rank_bonus": None, "unit_strength_per_model": None}

_RULE = {"node_type": "special_rule", "id": "fear", "name": "Fear",
         "text": "Units cause Fear.", "url": "https://example.com/special-rules/fear",
         "source_citation_book": "Core Rules", "source_citation_page": 10}

_UNIT = {"node_type": "unit", "id": "test-unit", "name": "Test Unit",
         "url": "https://example.com/unit/test-unit",
         "source_citation_book": "Test Book", "source_citation_page": 2,
         "troop_type_id": "regular-infantry",
         "unit_size_min": 10, "unit_size_max": 20,
         "base_width_mm": 25, "base_depth_mm": 25,
         "cost_points_per_model": 8, "army_category": "Core",
         "is_named_character": False, "wizard_level": None, "av_intrinsic": None,
         "unit_category": "Infantry", "last_updated": "2024-01-01"}

_PROFILE = {"node_type": "profile", "id": "test-unit#warrior",
            "name": "Warrior", "url": "https://example.com/unit/test-unit",
            "source_citation_book": "Test Book", "source_citation_page": 2,
            "M": 4, "WS": 3, "BS": 3, "S": 3, "T": 3, "W": 1, "I": 3, "A": 1, "Ld": 7,
            "order": 0}

_EDGES = [
    {"src": "test-unit", "dst": "test-army", "relation": "BELONGS_TO", "properties": {}},
    {"src": "test-unit", "dst": "regular-infantry", "relation": "HAS_TYPE", "properties": {}},
    {"src": "test-unit", "dst": "fear", "relation": "HAS_RULE", "properties": {}},
    {"src": "test-unit", "dst": "test-unit#warrior", "relation": "HAS_PROFILE",
     "properties": {"order": 0}},
]

_NODE_FILES = {
    "armies.json": [_ARMY],
    "troop_types.json": [_TROOP_TYPE],
    "units.json": [_UNIT],
    "profiles.json": [_PROFILE],
    "special_rules.json": [_RULE],
    "core_rules.json": [],
    "documents.json": [],
    "lores.json": [],
    "spells.json": [],
    "weapons.json": [],
    "magic_items.json": [],
    "faqs.json": [],
    "errata.json": [],
    "edges.json": _EDGES,
}


@pytest.fixture(scope="module")
def neo4j_container():
    with Neo4jContainer("neo4j:5.24-community").with_env(
        "NEO4J_PLUGINS", '["apoc"]'
    ) as container:
        yield container


@pytest.fixture(scope="module")
def parsed_dir(neo4j_container, tmp_path_factory):
    d = tmp_path_factory.mktemp("parsed")
    for filename, data in _NODE_FILES.items():
        (d / filename).write_text(json.dumps(data), encoding="utf-8")
    return d


@pytest.fixture(scope="module")
def driver(neo4j_container, parsed_dir, monkeypatch_module):
    bolt_url = neo4j_container.get_connection_url()
    monkeypatch_module.setenv("NEO4J_URI", bolt_url)
    monkeypatch_module.setenv("NEO4J_USER", "neo4j")
    monkeypatch_module.setenv("NEO4J_PASSWORD", neo4j_container.NEO4J_ADMIN_PASSWORD)
    monkeypatch_module.setenv("GRAPH_WIPE_ON_BUILD", "true")

    from pipeline.graph import client as _client
    _client._driver = None  # reset singleton
    d = _client.get_driver()
    yield d
    d.close()


@pytest.fixture(scope="module")
def monkeypatch_module(request):
    """Module-scoped monkeypatch (pytest monkeypatch is function-scoped by default)."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="module")
def build_report(driver, parsed_dir, monkeypatch_module):
    from pipeline.graph.builder import GraphBuilder

    monkeypatch_module.setattr(
        "pipeline.graph.builder._PARSED_DIR", parsed_dir, raising=True
    )
    return GraphBuilder().build()


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


class TestGraphBuild:
    def test_army_node_exists(self, driver, build_report) -> None:
        with driver.session() as s:
            rec = s.run("MATCH (n:Army {id: 'test-army'}) RETURN n.name AS name").single()
        assert rec is not None
        assert rec["name"] == "Test Army"

    def test_unit_node_exists(self, driver, build_report) -> None:
        with driver.session() as s:
            rec = s.run("MATCH (n:Unit {id: 'test-unit'}) RETURN n.name AS name").single()
        assert rec is not None

    def test_profile_node_exists(self, driver, build_report) -> None:
        with driver.session() as s:
            rec = s.run(
                "MATCH (n:Profile {id: 'test-unit#warrior'}) RETURN n.name AS name, n.M AS M"
            ).single()
        assert rec is not None
        assert rec["M"] == 4

    def test_has_profile_edge(self, driver, build_report) -> None:
        with driver.session() as s:
            rec = s.run(
                "MATCH (u:Unit {id: 'test-unit'})-[:HAS_PROFILE]->(p:Profile) "
                "RETURN p.name AS name, p.order AS ord"
            ).single()
        assert rec is not None
        assert rec["name"] == "Warrior"
        assert rec["ord"] == 0

    def test_belongs_to_edge(self, driver, build_report) -> None:
        with driver.session() as s:
            rec = s.run(
                "MATCH (u:Unit {id: 'test-unit'})-[:BELONGS_TO]->(a:Army) RETURN a.id AS aid"
            ).single()
        assert rec is not None
        assert rec["aid"] == "test-army"

    def test_has_rule_edge(self, driver, build_report) -> None:
        with driver.session() as s:
            rec = s.run(
                "MATCH (u:Unit {id: 'test-unit'})-[:HAS_RULE]->(r:SpecialRule) RETURN r.id AS rid"
            ).single()
        assert rec is not None
        assert rec["rid"] == "fear"

    def test_unit_flat_properties(self, driver, build_report) -> None:
        with driver.session() as s:
            rec = s.run(
                "MATCH (u:Unit {id: 'test-unit'}) "
                "RETURN u.base_width_mm AS bw, u.base_depth_mm AS bd, "
                "u.unit_size_min AS smin, u.unit_size_max AS smax, "
                "u.source_citation_book AS book"
            ).single()
        assert rec["bw"] == 25
        assert rec["bd"] == 25
        assert rec["smin"] == 10
        assert rec["smax"] == 20
        assert rec["book"] == "Test Book"

    def test_idempotency(self, driver, parsed_dir, monkeypatch_module) -> None:
        from pipeline.graph.builder import GraphBuilder

        monkeypatch_module.setattr(
            "pipeline.graph.builder._PARSED_DIR", parsed_dir, raising=True
        )
        monkeypatch_module.setenv("GRAPH_WIPE_ON_BUILD", "false")
        GraphBuilder().build()

        with driver.session() as s:
            unit_count = s.run("MATCH (n:Unit) RETURN count(n) AS c").single()["c"]
            army_count = s.run("MATCH (n:Army) RETURN count(n) AS c").single()["c"]
        assert unit_count == 1
        assert army_count == 1
