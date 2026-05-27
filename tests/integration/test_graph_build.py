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

_ARMY = {
    "node_type": "army",
    "id": "test-army",
    "name": "Test Army",
    "url": "https://example.com/army/test-army",
    "source_citation_book": "Test Book",
    "source_citation_page": 1,
}

_TROOP_TYPE = {
    "node_type": "troop_type",
    "id": "regular-infantry",
    "name": "Regular Infantry",
    "url": "https://example.com/troop-types/regular-infantry",
    "source_citation_book": "Core Rules",
    "source_citation_page": 5,
    "category": "Infantry",
    "min_models_for_rank_bonus": None,
    "max_rank_bonus": None,
    "unit_strength_per_model": None,
}

_RULE = {
    "node_type": "special_rule",
    "id": "fear",
    "name": "Fear",
    "text": "Units cause Fear.",
    "url": "https://example.com/special-rules/fear",
    "source_citation_book": "Core Rules",
    "source_citation_page": 10,
}

_UNIT = {
    "node_type": "unit",
    "id": "test-unit",
    "name": "Test Unit",
    "url": "https://example.com/unit/test-unit",
    "source_citation_book": "Test Book",
    "source_citation_page": 2,
    "troop_type_id": "regular-infantry",
    "unit_size_min": 10,
    "unit_size_max": 20,
    "base_width_mm": 25,
    "base_depth_mm": 25,
    "cost_points_per_model": 8,
    "army_category": "Core",
    "is_named_character": False,
    "wizard_level": None,
    "av_intrinsic": None,
    "unit_category": "Infantry",
    "last_updated": "2024-01-01",
}

_PROFILE = {
    "node_type": "profile",
    "id": "test-unit#warrior",
    "name": "Warrior",
    "url": "https://example.com/unit/test-unit",
    "source_citation_book": "Test Book",
    "source_citation_page": 2,
    "M": 4,
    "WS": 3,
    "BS": 3,
    "S": 3,
    "T": 3,
    "W": 1,
    "I": 3,
    "A": 1,
    "Ld": 7,
    "order": 0,
}

# ---------------------------------------------------------------------------
# Synthetic Upgrade nodes
# ---------------------------------------------------------------------------

_UPGRADE_BUDGET = {
    "node_type": "upgrade",
    "id": "test-unit#upgrade-magic-item-budget-test-army",
    "url": "https://example.com/unit/test-unit",
    "name": "Magic Item Budget (100 pts)",
    "description": "May take up to 100 points of magic items.",
    "upgrade_type": "magic_item_budget",
    "points_cost": None,
    "cost_unit": "budget",
    "points_budget": 100,
    "mutex_group": None,
    "applies_to_profile": None,
    "availability_constraint": None,
    "replaces_weapon_id": None,
    "bsb_unlimited_magic_standard": None,
    "order": 0,
    "source_citation_book": "Test Book",
    "source_citation_page": None,
}

# BSB upgrade for test-army (army 1)
_UPGRADE_BSB = {
    "node_type": "upgrade",
    "id": "test-unit#upgrade-bsb-test-army",
    "url": "https://example.com/unit/test-unit",
    "name": "Battle Standard Bearer",
    "description": "A single Test Unit may be upgraded to Battle Standard Bearer (+25 points).",
    "upgrade_type": "command_bsb",
    "points_cost": 25,
    "cost_unit": "flat",
    "points_budget": None,
    "mutex_group": None,
    "applies_to_profile": None,
    "availability_constraint": None,
    "replaces_weapon_id": None,
    "bsb_unlimited_magic_standard": True,
    "order": 1,
    "source_citation_book": "test-army",
    "source_citation_page": None,
}

# BSB upgrade for test-army-2 — same character slug, different army
# Tests that two distinct BSB upgrade IDs survive a build without merging into one.
_UPGRADE_BSB_2 = {
    "node_type": "upgrade",
    "id": "test-unit#upgrade-bsb-test-army-2",
    "url": "https://example.com/unit/test-unit",
    "name": "Battle Standard Bearer",
    "description": "A single Test Unit may be upgraded to Battle Standard Bearer (+25 points).",
    "upgrade_type": "command_bsb",
    "points_cost": 25,
    "cost_unit": "flat",
    "points_budget": None,
    "mutex_group": None,
    "applies_to_profile": None,
    "availability_constraint": None,
    "replaces_weapon_id": None,
    "bsb_unlimited_magic_standard": False,
    "order": 1,
    "source_citation_book": "test-army-2",
    "source_citation_page": None,
}

# ---------------------------------------------------------------------------
# Synthetic CompositionList / CompositionSlot nodes
# ---------------------------------------------------------------------------

_COMPOSITION_LIST = {
    "node_type": "composition_list",
    "id": "test-army#composition-list",
    "army_id": "test-army",
    "url": "https://example.com/army/test-army-army-list",
}

_COMPOSITION_SLOT = {
    "node_type": "composition_slot",
    "id": "test-army#composition-list#core",
    "composition_list_id": "test-army#composition-list",
    "army_id": "test-army",
    "slot_name": "Core",
    "min_pct": None,
    "max_pct": 50,
}

# ---------------------------------------------------------------------------
# Synthetic MagicItem nodes (for CAN_TAKE_ITEM derivation)
# ---------------------------------------------------------------------------

# Common magic weapon — accessible via magic_item_budget / command_bsb
_MAGIC_ITEM_COMMON = {
    "node_type": "magic_item",
    "id": "sword-of-power",
    "name": "Sword of Power",
    "item_type": "magic_weapon",
    "army_id": None,
    "cost": 50,
    "text": "A powerful sword.",
    "url": "https://example.com/magic-items/sword-of-power",
    "source_citation_book": "Test Book",
    "source_citation_page": None,
}

# Magic standard — excluded from magic_item_budget derivation
_MAGIC_ITEM_STANDARD = {
    "node_type": "magic_item",
    "id": "test-magic-standard",
    "name": "Test Magic Standard",
    "item_type": "magic_standard",
    "army_id": None,
    "cost": 25,
    "text": "A magic standard.",
    "url": "https://example.com/magic-items/test-magic-standard",
    "source_citation_book": "Test Book",
    "source_citation_page": None,
}

# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------

_EDGES = [
    {"src": "test-unit", "dst": "test-army", "relation": "BELONGS_TO", "properties": {}},
    {"src": "test-unit", "dst": "regular-infantry", "relation": "HAS_TYPE", "properties": {}},
    {"src": "test-unit", "dst": "fear", "relation": "HAS_RULE", "properties": {}},
    {
        "src": "test-unit",
        "dst": "test-unit#warrior",
        "relation": "HAS_PROFILE",
        "properties": {"order": 0},
    },
    # Upgrade edges
    {
        "src": "test-unit",
        "dst": "test-unit#upgrade-magic-item-budget-test-army",
        "relation": "HAS_UPGRADE",
        "properties": {},
    },
    {
        "src": "test-unit",
        "dst": "test-unit#upgrade-bsb-test-army",
        "relation": "HAS_UPGRADE",
        "properties": {},
    },
    {
        "src": "test-unit",
        "dst": "test-unit#upgrade-bsb-test-army-2",
        "relation": "HAS_UPGRADE",
        "properties": {},
    },
    # Composition edges
    {
        "src": "test-army",
        "dst": "test-army#composition-list",
        "relation": "HAS_LIST",
        "properties": {},
    },
    {
        "src": "test-army#composition-list",
        "dst": "test-army#composition-list#core",
        "relation": "HAS_SLOT",
        "properties": {},
    },
    {
        "src": "test-army#composition-list#core",
        "dst": "test-unit",
        "relation": "SLOT_ALLOWS",
        "properties": {},
    },
]

_NODE_FILES = {
    "armies.json": [_ARMY],
    "composition_lists.json": [_COMPOSITION_LIST],
    "composition_slots.json": [_COMPOSITION_SLOT],
    "troop_types.json": [_TROOP_TYPE],
    "units.json": [_UNIT],
    "profiles.json": [_PROFILE],
    "upgrades.json": [_UPGRADE_BUDGET, _UPGRADE_BSB, _UPGRADE_BSB_2],
    "special_rules.json": [_RULE],
    "core_rules.json": [],
    "documents.json": [],
    "lores.json": [],
    "spells.json": [],
    "weapons.json": [],
    "magic_items.json": [_MAGIC_ITEM_COMMON, _MAGIC_ITEM_STANDARD],
    "faqs.json": [],
    "errata.json": [],
    "edges.json": _EDGES,
}


@pytest.fixture(scope="module")
def neo4j_container():
    with Neo4jContainer("neo4j:5.24-community").with_env("NEO4J_PLUGINS", '["apoc"]') as container:
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
    monkeypatch_module.setenv("NEO4J_PASSWORD", neo4j_container.password)
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

    monkeypatch_module.setattr("pipeline.graph.builder._PARSED_DIR", parsed_dir, raising=True)
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

    # ------------------------------------------------------------------
    # Upgrade nodes
    # ------------------------------------------------------------------

    def test_upgrade_node_exists(self, driver, build_report) -> None:
        with driver.session() as s:
            rec = s.run(
                "MATCH (n:Upgrade {id: 'test-unit#upgrade-magic-item-budget-test-army'}) "
                "RETURN n.upgrade_type AS ut, n.points_budget AS pb"
            ).single()
        assert rec is not None
        assert rec["ut"] == "magic_item_budget"
        assert rec["pb"] == 100

    def test_has_upgrade_edge(self, driver, build_report) -> None:
        with driver.session() as s:
            count = s.run(
                "MATCH (u:Unit {id: 'test-unit'})-[:HAS_UPGRADE]->(up:Upgrade) "
                "RETURN count(up) AS c"
            ).single()["c"]
        assert count == 3  # magic_item_budget + bsb-test-army + bsb-test-army-2

    # ------------------------------------------------------------------
    # CompositionList / CompositionSlot
    # ------------------------------------------------------------------

    def test_composition_list_node(self, driver, build_report) -> None:
        with driver.session() as s:
            rec = s.run(
                "MATCH (n:CompositionList {id: 'test-army#composition-list'}) "
                "RETURN n.army_id AS aid"
            ).single()
        assert rec is not None
        assert rec["aid"] == "test-army"

    def test_composition_slot_node(self, driver, build_report) -> None:
        with driver.session() as s:
            rec = s.run(
                "MATCH (n:CompositionSlot {id: 'test-army#composition-list#core'}) "
                "RETURN n.slot_name AS sn, n.max_pct AS mp"
            ).single()
        assert rec is not None
        assert rec["sn"] == "Core"
        assert rec["mp"] == 50

    def test_has_list_and_slot_edges(self, driver, build_report) -> None:
        with driver.session() as s:
            rec = s.run(
                "MATCH (:Army {id: 'test-army'})-[:HAS_LIST]->(cl:CompositionList)"
                "-[:HAS_SLOT]->(cs:CompositionSlot) "
                "RETURN cs.slot_name AS sn"
            ).single()
        assert rec is not None
        assert rec["sn"] == "Core"

    # ------------------------------------------------------------------
    # CAN_TAKE_ITEM derivation
    # ------------------------------------------------------------------

    def test_can_take_item_derived(self, driver, build_report) -> None:
        with driver.session() as s:
            rec = s.run(
                "MATCH (u:Unit {id: 'test-unit'})-[r:CAN_TAKE_ITEM]->"
                "(i:MagicItem {id: 'sword-of-power'}) "
                "RETURN r.budget AS budget, r.unlimited AS unlimited"
            ).single()
        assert rec is not None
        assert rec["budget"] == 100
        assert rec["unlimited"] is False

    def test_can_take_item_includes_magic_standard_for_bsb(self, driver, build_report) -> None:
        with driver.session() as s:
            rec = s.run(
                "MATCH (u:Unit {id: 'test-unit'})-[r:CAN_TAKE_ITEM]->"
                "(i:MagicItem {item_type: 'magic_standard'}) "
                "RETURN r.budget AS budget, r.unlimited AS unlimited, i.id AS iid"
            ).single()
        assert rec is not None
        assert rec["iid"] == "test-magic-standard"
        assert rec["budget"] is None
        assert rec["unlimited"] is True

    # ------------------------------------------------------------------
    # BSB cross-army uniqueness
    # ------------------------------------------------------------------

    def test_bsb_upgrade_unique_per_army(self, driver, build_report) -> None:
        # Two distinct BSB upgrades (one per army slug in id) must each exist exactly once.
        with driver.session() as s:
            bsb_ids = [
                r["iid"]
                for r in s.run(
                    "MATCH (u:Unit {id: 'test-unit'})-[:HAS_UPGRADE]->(up:Upgrade) "
                    "WHERE up.upgrade_type = 'command_bsb' "
                    "RETURN up.id AS iid"
                )
            ]
        assert sorted(bsb_ids) == [
            "test-unit#upgrade-bsb-test-army",
            "test-unit#upgrade-bsb-test-army-2",
        ]

    # ------------------------------------------------------------------
    # Idempotency (second full build must not duplicate any node or edge)
    # ------------------------------------------------------------------

    def test_idempotency(self, driver, parsed_dir, monkeypatch_module) -> None:
        from pipeline.graph.builder import GraphBuilder

        monkeypatch_module.setattr("pipeline.graph.builder._PARSED_DIR", parsed_dir, raising=True)
        monkeypatch_module.setenv("GRAPH_WIPE_ON_BUILD", "false")
        GraphBuilder().build()

        with driver.session() as s:
            unit_count = s.run("MATCH (n:Unit) RETURN count(n) AS c").single()["c"]
            army_count = s.run("MATCH (n:Army) RETURN count(n) AS c").single()["c"]
            upgrade_count = s.run("MATCH (n:Upgrade) RETURN count(n) AS c").single()["c"]
            can_take_count = s.run(
                "MATCH (u:Unit {id: 'test-unit'})-[:CAN_TAKE_ITEM]->(:MagicItem) "
                "RETURN count(*) AS c"
            ).single()["c"]
        assert unit_count == 1
        assert army_count == 1
        assert upgrade_count == 3
        assert can_take_count == 2  # sword-of-power + test-magic-standard (BSB), not doubled
