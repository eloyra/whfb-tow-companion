"""
Tests for pipeline/scraper/parsers/_options.py:
parse_options_to_upgrades() — upgrade type classification, cost extraction,
mutex groups, profile scoping, and edge emission.
"""

from __future__ import annotations

import pytest

from pipeline.constants import EdgeType
from pipeline.scraper.parsers._options import parse_options_to_upgrades

_SC = {"source_citation_book": "test-army", "source_citation_page": None}


# ---------------------------------------------------------------------------
# Rich-text builder helpers
# ---------------------------------------------------------------------------


def _make_doc(*items: dict) -> dict:
    return {
        "nodeType": "document",
        "content": [{"nodeType": "unordered-list", "content": list(items)}],
    }


def _item(
    text: str,
    links: list[tuple[str, str]] | None = None,
    nested: list[dict] | None = None,
) -> dict:
    para_content: list[dict] = [{"nodeType": "text", "value": text}]
    for slug, ct in links or []:
        para_content.append({
            "nodeType": "entry-hyperlink",
            "data": {
                "target": {
                    "fields": {"slug": slug},
                    "sys": {"contentType": {"sys": {"id": ct}}},
                }
            },
            "content": [{"nodeType": "text", "value": slug}],
        })
    body: list[dict] = [{"nodeType": "paragraph", "content": para_content}]
    if nested:
        body.append({"nodeType": "unordered-list", "content": nested})
    return {"nodeType": "list-item", "content": body}


def _group(header: str, *children: dict) -> dict:
    """Parent list-item with header paragraph + nested child items."""
    return _item(header, nested=list(children))


# ---------------------------------------------------------------------------
# Cost extraction
# ---------------------------------------------------------------------------


class TestCostExtraction:
    def test_flat_cost(self) -> None:
        doc = _make_doc(_item("Shield (+2 points)", [("shield", "rule")]))
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades[0]["points_cost"] == 2
        assert upgrades[0]["cost_unit"] == "flat"

    def test_per_model_cost(self) -> None:
        doc = _make_doc(_item("Great weapon (+3 points per model)", [("great-weapon", "rule")]))
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades[0]["points_cost"] == 3
        assert upgrades[0]["cost_unit"] == "per_model"

    def test_per_unit_cost(self) -> None:
        doc = _make_doc(_item("Upgrade one model to a standard bearer (+6 points per unit)"))
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades[0]["points_cost"] == 6
        assert upgrades[0]["cost_unit"] == "per_unit"

    def test_no_cost(self) -> None:
        doc = _make_doc(_item("Free rule"))
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades[0]["points_cost"] is None
        assert upgrades[0]["cost_unit"] is None


# ---------------------------------------------------------------------------
# Budget classification
# ---------------------------------------------------------------------------


class TestBudgetClassification:
    def test_magic_item_budget(self) -> None:
        doc = _make_doc(_item("May take up to 100 points of magic items."))
        upgrades, _ = parse_options_to_upgrades("vampire-count", doc, set(), _SC)
        assert upgrades[0]["upgrade_type"] == "magic_item_budget"
        assert upgrades[0]["points_budget"] == 100
        assert upgrades[0]["cost_unit"] == "budget"

    def test_vampiric_powers_budget(self) -> None:
        doc = _make_doc(
            _item(
                "May take up to 100 points of Vampiric Powers.",
                [("vampiric-powers", "rule")],
            )
        )
        upgrades, _ = parse_options_to_upgrades("vampire-count", doc, set(), _SC)
        assert upgrades[0]["upgrade_type"] == "vampiric_powers_budget"
        assert upgrades[0]["points_budget"] == 100

    def test_rune_budget(self) -> None:
        doc = _make_doc(
            _item(
                "May take up to 75 points of weapon runes.",
                [("weapon-runes", "rule")],
            )
        )
        upgrades, _ = parse_options_to_upgrades("thane", doc, set(), _SC)
        assert upgrades[0]["upgrade_type"] == "rune_budget"
        assert upgrades[0]["points_budget"] == 75

    def test_magic_standard_budget(self) -> None:
        doc = _make_doc(_item("May carry a magic standard worth up to 50 points."))
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades[0]["upgrade_type"] == "magic_standard_budget"
        assert upgrades[0]["points_budget"] == 50

    def test_budget_name_includes_pts(self) -> None:
        doc = _make_doc(_item("May take up to 100 points of magic items."))
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert "100" in upgrades[0]["name"]


# ---------------------------------------------------------------------------
# Wizard level
# ---------------------------------------------------------------------------


class TestWizardLevel:
    def test_wizard_type(self) -> None:
        doc = _make_doc(_item("May be a Level 2 Wizard (+35 points)"))
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades[0]["upgrade_type"] == "wizard_level"

    def test_wizard_cost(self) -> None:
        doc = _make_doc(_item("May be a Level 2 Wizard (+35 points)"))
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades[0]["points_cost"] == 35

    def test_wizard_name_format(self) -> None:
        doc = _make_doc(_item("May be a Level 4 Wizard (+100 points)"))
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades[0]["name"] == "Level 4 Wizard"


# ---------------------------------------------------------------------------
# Command group (grave-guard style)
# ---------------------------------------------------------------------------


class TestCommandGroup:
    def _make_doc(self) -> dict:
        return _make_doc(
            _item(
                "Upgrade one model to a Seneschal (+6 points per unit)",
                [("seneschal-of-the-grave-guard", "rule")],
            ),
            _item("Upgrade one model to a standard bearer (+6 points per unit)"),
            _item("Upgrade one model to a Danse Macabre (musician) (+6 points per unit)"),
        )

    def test_champion_type(self) -> None:
        upgrades, _ = parse_options_to_upgrades("grave-guard", self._make_doc(), set(), _SC)
        assert upgrades[0]["upgrade_type"] == "command_champion"

    def test_standard_type(self) -> None:
        upgrades, _ = parse_options_to_upgrades("grave-guard", self._make_doc(), set(), _SC)
        assert upgrades[1]["upgrade_type"] == "command_standard"

    def test_named_musician_type(self) -> None:
        upgrades, _ = parse_options_to_upgrades("grave-guard", self._make_doc(), set(), _SC)
        assert upgrades[2]["upgrade_type"] == "command_musician"

    def test_command_cost_per_unit(self) -> None:
        upgrades, _ = parse_options_to_upgrades("grave-guard", self._make_doc(), set(), _SC)
        for up in upgrades:
            assert up["points_cost"] == 6
            assert up["cost_unit"] == "per_unit"


# ---------------------------------------------------------------------------
# Mutex groups
# ---------------------------------------------------------------------------


class TestMutexGroup:
    def test_mutex_siblings_share_group(self) -> None:
        doc = _make_doc(
            _group(
                "May take one of the following:",
                _item("Great weapon (+4 points per model)", [("great-weapon", "rule")]),
                _item("Halberd (+2 points per model)", [("halberd", "rule")]),
            )
        )
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert len(upgrades) == 2
        assert upgrades[0]["mutex_group"] is not None
        assert upgrades[0]["mutex_group"] == upgrades[1]["mutex_group"]

    def test_mutex_group_id_contains_unit_slug(self) -> None:
        doc = _make_doc(
            _group(
                "May take one of the following:",
                _item("Sword (+1 points)", [("sword", "rule")]),
            )
        )
        upgrades, _ = parse_options_to_upgrades("my-unit", doc, set(), _SC)
        assert "my-unit" in upgrades[0]["mutex_group"]

    def test_non_mutex_header_no_mutex_group(self) -> None:
        doc = _make_doc(
            _group(
                "May take any of the following:",
                _item("Shield (+2 points)", [("shield", "rule")]),
                _item("Spear (+1 points)", [("spear", "rule")]),
            )
        )
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades[0]["mutex_group"] is None

    def test_multiple_mutex_groups_distinct(self) -> None:
        doc = _make_doc(
            _group(
                "May take one of the following:",
                _item("Option A (+1 points)", [("option-a", "rule")]),
            ),
            _group(
                "May take one of the following:",
                _item("Option B (+1 points)", [("option-b", "rule")]),
            ),
        )
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades[0]["mutex_group"] != upgrades[1]["mutex_group"]


# ---------------------------------------------------------------------------
# Profile scoping
# ---------------------------------------------------------------------------


class TestProfileScope:
    def test_group_header_sets_applies_to_profile(self) -> None:
        profile_set = {"grave-guard#seneschal"}
        doc = _make_doc(
            _group(
                "A Seneschal may purchase:",
                _item("May take up to 25 points of magic items."),
            )
        )
        upgrades, _ = parse_options_to_upgrades("grave-guard", doc, profile_set, _SC)
        assert upgrades[0]["applies_to_profile"] == "grave-guard#seneschal"

    def test_unknown_profile_not_set(self) -> None:
        doc = _make_doc(
            _group(
                "A Unknown Character may purchase:",
                _item("May take up to 25 points of magic items."),
            )
        )
        upgrades, _ = parse_options_to_upgrades("grave-guard", doc, set(), _SC)
        assert upgrades[0]["applies_to_profile"] is None

    def test_top_level_scoped_item(self) -> None:
        profile_set = {"unit#hero"}
        doc = _make_doc(_item("A Hero may take up to 50 points of magic items."))
        upgrades, _ = parse_options_to_upgrades("unit", doc, profile_set, _SC)
        assert upgrades[0]["applies_to_profile"] == "unit#hero"


# ---------------------------------------------------------------------------
# Mount classification
# ---------------------------------------------------------------------------


class TestMountClassification:
    def test_armylistentry_link_is_mount(self) -> None:
        doc = _make_doc(
            _item("May be mounted on a Nightmare (+30 points)", [("nightmare", "armyListEntry")])
        )
        upgrades, edges = parse_options_to_upgrades("wight-king", doc, set(), _SC)
        assert upgrades[0]["upgrade_type"] == "mount"

    def test_unlocks_mount_edge_emitted(self) -> None:
        doc = _make_doc(
            _item("May be mounted on a Nightmare (+30 points)", [("nightmare", "armyListEntry")])
        )
        _, edges = parse_options_to_upgrades("wight-king", doc, set(), _SC)
        mount_edges = [e for e in edges if e["relation"] == EdgeType.UNLOCKS_MOUNT]
        assert len(mount_edges) == 1
        assert mount_edges[0]["dst"] == "nightmare"

    def test_mount_group_header_force_mount(self) -> None:
        doc = _make_doc(
            _group(
                "May be mounted on one of the following:",
                _item("Nightmare (+30 points)", [("nightmare", "armyListEntry")]),
                _item("Hellsteed (+40 points)", [("hellsteed", "armyListEntry")]),
            )
        )
        upgrades, _ = parse_options_to_upgrades("vampire-count", doc, set(), _SC)
        assert all(u["upgrade_type"] == "mount" for u in upgrades)


# ---------------------------------------------------------------------------
# Equipment swap
# ---------------------------------------------------------------------------


class TestEquipmentSwap:
    def test_weapon_replace_type(self) -> None:
        doc = _make_doc(
            _item(
                "Replace hand weapon with great weapon (+3 points per model)",
                [("hand-weapon", "rule"), ("great-weapon", "rule")],
            )
        )
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades[0]["upgrade_type"] == "weapon_replace"

    def test_replaces_weapon_id_set(self) -> None:
        doc = _make_doc(
            _item(
                "Replace hand weapon with great weapon (+3 points per model)",
                [("hand-weapon", "rule"), ("great-weapon", "rule")],
            )
        )
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades[0]["replaces_weapon_id"] == "hand-weapon"

    def test_replaces_weapon_edge(self) -> None:
        doc = _make_doc(
            _item(
                "Replace spear with lance (+5 points per model)",
                [("spear", "rule"), ("lance", "rule")],
            )
        )
        _, edges = parse_options_to_upgrades("unit", doc, set(), _SC)
        replaces = [e for e in edges if e["relation"] == EdgeType.REPLACES_WEAPON]
        assert len(replaces) == 1
        assert replaces[0]["dst"] == "spear"

    def test_replacement_weapon_has_unlocks_rule_edge(self) -> None:
        doc = _make_doc(
            _item(
                "Replace spear with lance (+5 points per model)",
                [("spear", "rule"), ("lance", "rule")],
            )
        )
        _, edges = parse_options_to_upgrades("unit", doc, set(), _SC)
        unlocks = [e for e in edges if e["relation"] == EdgeType.UNLOCKS_RULE]
        assert any(e["dst"] == "lance" for e in unlocks)


# ---------------------------------------------------------------------------
# Edge structure invariants
# ---------------------------------------------------------------------------


class TestEdgeStructure:
    def test_has_upgrade_edge_per_upgrade(self) -> None:
        doc = _make_doc(
            _item("Shield (+2 points)", [("shield", "rule")]),
            _item("Spear (+1 points)", [("spear", "rule")]),
        )
        upgrades, edges = parse_options_to_upgrades("unit-x", doc, set(), _SC)
        has_upgrade = [e for e in edges if e["relation"] == EdgeType.HAS_UPGRADE]
        assert len(has_upgrade) == 2
        assert all(e["src"] == "unit-x" for e in has_upgrade)
        upgrade_ids = {u["id"] for u in upgrades}
        assert {e["dst"] for e in has_upgrade} == upgrade_ids

    def test_upgrade_order_sequential(self) -> None:
        doc = _make_doc(
            _item("First item"),
            _item("Second item"),
            _item("Third item"),
        )
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert [u["order"] for u in upgrades] == [0, 1, 2]

    def test_none_options_returns_empty(self) -> None:
        upgrades, edges = parse_options_to_upgrades("unit", None, set(), _SC)
        assert upgrades == []
        assert edges == []

    def test_no_list_in_doc_returns_empty(self) -> None:
        doc = {"nodeType": "document", "content": [{"nodeType": "paragraph", "content": []}]}
        upgrades, edges = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades == []
        assert edges == []

    def test_nested_group_upgrades_inherit_availability_constraint(self) -> None:
        doc = _make_doc(
            _group(
                "0-1 unit per 1,000 points may:",
                _item("Shield (+2 points)", [("shield", "rule")]),
            )
        )
        upgrades, _ = parse_options_to_upgrades("unit", doc, set(), _SC)
        assert upgrades[0]["availability_constraint"] is not None
        assert "0-1" in upgrades[0]["availability_constraint"]
