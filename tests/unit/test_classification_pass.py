"""
Tests for the two-pass edge relabeling and upgrade-type promotion logic
used by the parse coordinator (pipeline/scraper/parsers/__init__.py).

The coordinator embeds this logic inline in run_all_parsers(), so these tests
replicate the algorithm against synthetic data to verify correctness without
going through the full filesystem-coupled pipeline.
"""

from __future__ import annotations

from pipeline.constants import EdgeType


# ---------------------------------------------------------------------------
# Simulate the coordinator two-pass classifier
# ---------------------------------------------------------------------------


def _apply_two_pass(
    all_edges: list[dict],
    nodes_by_type: dict[str, list[dict]],
) -> tuple[list[dict], dict[str, list[dict]]]:
    """Mirrors the two-pass logic in run_all_parsers() for unit testing."""
    weapon_slugs: set[str] = {n["id"] for n in nodes_by_type.get("weapon", []) if "id" in n}
    item_slugs: set[str] = {n["id"] for n in nodes_by_type.get("magic_item", []) if "id" in n}

    # Pass 1 — relabel provisional UNLOCKS_RULE edges
    for edge in all_edges:
        if edge.get("relation") == EdgeType.UNLOCKS_RULE:
            dst = edge.get("dst", "")
            if dst in weapon_slugs:
                edge["relation"] = EdgeType.UNLOCKS_WEAPON
            elif dst in item_slugs:
                edge["relation"] = EdgeType.UNLOCKS_ITEM

    # Pass 2 — promote rule_add upgrades that have weapon/mount edges to weapon_add
    upgrades_with_weapon_edge: set[str] = {
        e["src"]
        for e in all_edges
        if e.get("relation") in (EdgeType.UNLOCKS_WEAPON, EdgeType.UNLOCKS_MOUNT)
    }
    for node in nodes_by_type.get("upgrade", []):
        if (
            node.get("upgrade_type") == "rule_add"
            and node.get("id") in upgrades_with_weapon_edge
        ):
            node["upgrade_type"] = "weapon_add"

    return all_edges, nodes_by_type


def _edge(src: str, dst: str, relation: str) -> dict:
    return {"src": src, "dst": dst, "relation": relation, "properties": {}}


# ---------------------------------------------------------------------------
# UNLOCKS_RULE relabeling
# ---------------------------------------------------------------------------


class TestUnlocksRuleRelabeling:
    def test_rule_to_weapon_when_dst_in_weapon_slugs(self) -> None:
        edges = [_edge("up1", "great-sword", EdgeType.UNLOCKS_RULE)]
        nodes = {"weapon": [{"id": "great-sword"}], "magic_item": []}
        result_edges, _ = _apply_two_pass(edges, nodes)
        assert result_edges[0]["relation"] == EdgeType.UNLOCKS_WEAPON

    def test_rule_to_item_when_dst_in_item_slugs(self) -> None:
        edges = [_edge("up1", "sword-of-kings", EdgeType.UNLOCKS_RULE)]
        nodes = {"weapon": [], "magic_item": [{"id": "sword-of-kings"}]}
        result_edges, _ = _apply_two_pass(edges, nodes)
        assert result_edges[0]["relation"] == EdgeType.UNLOCKS_ITEM

    def test_rule_stays_when_dst_in_neither(self) -> None:
        edges = [_edge("up1", "some-special-rule", EdgeType.UNLOCKS_RULE)]
        nodes = {"weapon": [], "magic_item": []}
        result_edges, _ = _apply_two_pass(edges, nodes)
        assert result_edges[0]["relation"] == EdgeType.UNLOCKS_RULE

    def test_non_rule_edges_not_touched(self) -> None:
        edges = [_edge("unit", "up1", EdgeType.HAS_UPGRADE)]
        nodes = {"weapon": [{"id": "up1"}]}
        result_edges, _ = _apply_two_pass(edges, nodes)
        assert result_edges[0]["relation"] == EdgeType.HAS_UPGRADE

    def test_weapon_checked_before_item_when_slug_in_both(self) -> None:
        edges = [_edge("up1", "dual-slug", EdgeType.UNLOCKS_RULE)]
        nodes = {
            "weapon": [{"id": "dual-slug"}],
            "magic_item": [{"id": "dual-slug"}],
        }
        result_edges, _ = _apply_two_pass(edges, nodes)
        assert result_edges[0]["relation"] == EdgeType.UNLOCKS_WEAPON

    def test_multiple_edges_each_relabeled_independently(self) -> None:
        edges = [
            _edge("up1", "sword", EdgeType.UNLOCKS_RULE),
            _edge("up2", "ring-of-power", EdgeType.UNLOCKS_RULE),
            _edge("up3", "general-rule", EdgeType.UNLOCKS_RULE),
        ]
        nodes = {
            "weapon": [{"id": "sword"}],
            "magic_item": [{"id": "ring-of-power"}],
        }
        result_edges, _ = _apply_two_pass(edges, nodes)
        by_src = {e["src"]: e["relation"] for e in result_edges}
        assert by_src["up1"] == EdgeType.UNLOCKS_WEAPON
        assert by_src["up2"] == EdgeType.UNLOCKS_ITEM
        assert by_src["up3"] == EdgeType.UNLOCKS_RULE

    def test_replaces_weapon_edge_not_changed(self) -> None:
        edges = [_edge("up1", "sword", EdgeType.REPLACES_WEAPON)]
        nodes = {"weapon": [{"id": "sword"}]}
        result_edges, _ = _apply_two_pass(edges, nodes)
        assert result_edges[0]["relation"] == EdgeType.REPLACES_WEAPON


# ---------------------------------------------------------------------------
# rule_add → weapon_add promotion
# ---------------------------------------------------------------------------


class TestWeaponAddPromotion:
    def test_rule_add_with_unlocks_weapon_promoted(self) -> None:
        upgrade = {"id": "up1", "upgrade_type": "rule_add"}
        edges = [
            _edge("unit", "up1", EdgeType.HAS_UPGRADE),
            _edge("up1", "great-sword", EdgeType.UNLOCKS_WEAPON),
        ]
        nodes = {"weapon": [{"id": "great-sword"}], "upgrade": [upgrade]}
        _, result_nodes = _apply_two_pass(edges, nodes)
        assert result_nodes["upgrade"][0]["upgrade_type"] == "weapon_add"

    def test_rule_add_with_unlocks_mount_promoted(self) -> None:
        upgrade = {"id": "up1", "upgrade_type": "rule_add"}
        edges = [_edge("up1", "nightmare", EdgeType.UNLOCKS_MOUNT)]
        nodes = {"weapon": [], "magic_item": [], "upgrade": [upgrade]}
        _, result_nodes = _apply_two_pass(edges, nodes)
        assert result_nodes["upgrade"][0]["upgrade_type"] == "weapon_add"

    def test_rule_add_without_weapon_or_mount_edge_stays(self) -> None:
        upgrade = {"id": "up1", "upgrade_type": "rule_add"}
        edges = [_edge("up1", "some-rule", EdgeType.UNLOCKS_RULE)]
        nodes = {"weapon": [], "magic_item": [], "upgrade": [upgrade]}
        _, result_nodes = _apply_two_pass(edges, nodes)
        assert result_nodes["upgrade"][0]["upgrade_type"] == "rule_add"

    def test_non_rule_add_type_not_promoted(self) -> None:
        upgrade = {"id": "up1", "upgrade_type": "command_champion"}
        edges = [_edge("up1", "great-sword", EdgeType.UNLOCKS_WEAPON)]
        nodes = {"weapon": [{"id": "great-sword"}], "upgrade": [upgrade]}
        _, result_nodes = _apply_two_pass(edges, nodes)
        assert result_nodes["upgrade"][0]["upgrade_type"] == "command_champion"

    def test_promotion_uses_post_relabeling_edges(self) -> None:
        # up1 has UNLOCKS_RULE → great-sword; after pass 1, it becomes UNLOCKS_WEAPON
        # pass 2 should then promote up1 to weapon_add
        upgrade = {"id": "up1", "upgrade_type": "rule_add"}
        edges = [_edge("up1", "great-sword", EdgeType.UNLOCKS_RULE)]
        nodes = {
            "weapon": [{"id": "great-sword"}],
            "magic_item": [],
            "upgrade": [upgrade],
        }
        _, result_nodes = _apply_two_pass(edges, nodes)
        assert result_nodes["upgrade"][0]["upgrade_type"] == "weapon_add"

    def test_multiple_upgrades_promoted_independently(self) -> None:
        upgrades = [
            {"id": "up1", "upgrade_type": "rule_add"},
            {"id": "up2", "upgrade_type": "rule_add"},
        ]
        edges = [
            _edge("up1", "sword", EdgeType.UNLOCKS_WEAPON),
            # up2 has no weapon edge
            _edge("up2", "magic-rule", EdgeType.UNLOCKS_RULE),
        ]
        nodes = {"weapon": [{"id": "sword"}], "magic_item": [], "upgrade": upgrades}
        _, result_nodes = _apply_two_pass(edges, nodes)
        by_id = {u["id"]: u["upgrade_type"] for u in result_nodes["upgrade"]}
        assert by_id["up1"] == "weapon_add"
        assert by_id["up2"] == "rule_add"
