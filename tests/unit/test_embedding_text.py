"""
Tests for per-label embedding text builders (pipeline/embeddings/text.py).

Uses a fake Neo4j driver to avoid real database connectivity.  Each builder
is exercised with a single ID to verify the text contains the expected fields
in the expected order / format.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from pipeline.embeddings import text as text_builder

# ---------------------------------------------------------------------------
# Fake driver helpers
# ---------------------------------------------------------------------------


def _make_driver(records_per_call: list[list[dict]]) -> MagicMock:
    """Return a mock driver whose session().run() cycles through record lists.

    Each call to ``session.run(...)`` pops the next list from *records_per_call*
    and returns it (wrapped in a mock result).
    """
    call_count = [0]
    all_calls = records_per_call

    def run_side_effect(query: str, **kwargs: Any):
        idx = call_count[0]
        call_count[0] += 1
        batch = all_calls[idx] if idx < len(all_calls) else []
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter(batch))
        return mock_result

    session = MagicMock()
    session.run.side_effect = run_side_effect
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    driver = MagicMock()
    driver.session.return_value = session
    return driver


# ---------------------------------------------------------------------------
# SpecialRule / CoreRule / Document  (name + text)
# ---------------------------------------------------------------------------


class TestFormatNameText:
    def test_special_rule(self) -> None:
        driver = _make_driver([[{"nid": "fear", "name": "Fear", "text": "Units cause Fear."}]])
        texts = text_builder.build_for_label(driver, "SpecialRule", ["fear"])
        assert texts == ["Fear. Units cause Fear."]

    def test_core_rule(self) -> None:
        driver = _make_driver(
            [[{"nid": "movement", "name": "Movement", "text": "Move in M phase."}]]
        )
        texts = text_builder.build_for_label(driver, "CoreRule", ["movement"])
        assert texts == ["Movement. Move in M phase."]

    def test_document(self) -> None:
        driver = _make_driver([[{"nid": "intro", "name": "Introduction", "text": "Welcome text."}]])
        texts = text_builder.build_for_label(driver, "Document", ["intro"])
        assert texts == ["Introduction. Welcome text."]

    def test_missing_text_field(self) -> None:
        driver = _make_driver([[{"nid": "x", "name": "X", "text": None}]])
        texts = text_builder.build_for_label(driver, "SpecialRule", ["x"])
        assert texts == ["X"]

    def test_unknown_label_falls_back_to_name_only(self) -> None:
        driver = _make_driver([[{"nid": "z", "name": "Zephyr"}]])
        texts = text_builder.build_for_label(driver, "UnknownLabel", ["z"])
        assert texts == ["Zephyr"]


# ---------------------------------------------------------------------------
# TroopType
# ---------------------------------------------------------------------------


class TestTroopType:
    def test_full_fields(self) -> None:
        driver = _make_driver(
            [
                [
                    {
                        "nid": "heavy-cavalry",
                        "name": "Heavy Cavalry",
                        "category": "Cavalry",
                        "min_rank": 3,
                        "max_rank": 3,
                        "strength": 2,
                        "text": "Mounted on barded steeds.",
                    }
                ]
            ]
        )
        texts = text_builder.build_for_label(driver, "TroopType", ["heavy-cavalry"])
        t = texts[0]
        assert "Heavy Cavalry" in t
        assert "Cavalry" in t
        assert "Rank bonus min 3" in t
        assert "max +3" in t
        assert "Unit strength 2" in t
        assert "Mounted on barded steeds." in t

    def test_missing_optional_fields(self) -> None:
        driver = _make_driver(
            [
                [
                    {
                        "nid": "x",
                        "name": "X",
                        "category": None,
                        "min_rank": None,
                        "max_rank": None,
                        "strength": None,
                        "text": None,
                    }
                ]
            ]
        )
        texts = text_builder.build_for_label(driver, "TroopType", ["x"])
        assert texts == ["X"]


# ---------------------------------------------------------------------------
# Spell
# ---------------------------------------------------------------------------


class TestSpell:
    def test_includes_lore(self) -> None:
        driver = _make_driver(
            [
                [
                    {
                        "nid": "fireball",
                        "name": "Fireball",
                        "text": "Deals fire damage.",
                        "lore_name": "Fire",
                    }
                ]
            ]
        )
        texts = text_builder.build_for_label(driver, "Spell", ["fireball"])
        t = texts[0]
        assert "Fireball" in t
        assert "Lore of Fire" in t
        assert "Deals fire damage." in t

    def test_no_lore(self) -> None:
        driver = _make_driver(
            [[{"nid": "fireball", "name": "Fireball", "text": "Damage.", "lore_name": None}]]
        )
        texts = text_builder.build_for_label(driver, "Spell", ["fireball"])
        assert "Lore of" not in texts[0]


# ---------------------------------------------------------------------------
# MagicItem
# ---------------------------------------------------------------------------


class TestMagicItem:
    def test_full_fields(self) -> None:
        driver = _make_driver(
            [
                [
                    {
                        "nid": "sword-of-kings",
                        "name": "Sword of Kings",
                        "item_type": "magic_weapon",
                        "cost": 50,
                        "text": "A legendary blade.",
                    }
                ]
            ]
        )
        texts = text_builder.build_for_label(driver, "MagicItem", ["sword-of-kings"])
        t = texts[0]
        assert "Sword of Kings" in t
        assert "magic weapon" in t
        assert "50 pts" in t
        assert "A legendary blade." in t


# ---------------------------------------------------------------------------
# Lore
# ---------------------------------------------------------------------------


class TestLore:
    def test_includes_spells(self) -> None:
        driver = _make_driver(
            [
                [
                    {
                        "nid": "lore-of-fire",
                        "name": "Fire",
                        "text": "Fire lore text.",
                        "spell_names": ["Fireball", "Wall of Fire"],
                    }
                ]
            ]
        )
        texts = text_builder.build_for_label(driver, "Lore", ["lore-of-fire"])
        t = texts[0]
        assert "Fire" in t
        assert "Fire lore text." in t
        assert "Fireball" in t
        assert "Wall of Fire" in t


# ---------------------------------------------------------------------------
# FAQ / Errata
# ---------------------------------------------------------------------------


class TestFaq:
    def test_question_and_answer(self) -> None:
        driver = _make_driver(
            [[{"nid": "q1", "question": "Can a unit march?", "answer": 'Yes, if not in 8".'}]]
        )
        texts = text_builder.build_for_label(driver, "FAQ", ["q1"])
        assert "Can a unit march?" in texts[0]
        assert 'Yes, if not in 8".' in texts[0]


class TestErrata:
    def test_original_and_corrected(self) -> None:
        driver = _make_driver(
            [
                [
                    {
                        "nid": "e1",
                        "name": "Correction 1",
                        "original": "Wrong text.",
                        "corrected": "Correct text.",
                    }
                ]
            ]
        )
        texts = text_builder.build_for_label(driver, "Errata", ["e1"])
        t = texts[0]
        assert "Correction 1" in t
        assert "Original: Wrong text." in t
        assert "Corrected: Correct text." in t


# ---------------------------------------------------------------------------
# Weapon
# ---------------------------------------------------------------------------


class TestWeapon:
    def test_ranged_weapon(self) -> None:
        driver = _make_driver(
            [
                [
                    {
                        "nid": "crossbow",
                        "name": "Crossbow",
                        "weapon_class": "ranged_weapon",
                        "range": 30,
                        "strength": 4,
                        "ap": 1,
                        "shots": 1,
                        "armour_value": None,
                        "special_rules": ["Armour Bane (1)"],
                        "text": "A powerful crossbow.",
                    }
                ]
            ]
        )
        texts = text_builder.build_for_label(driver, "Weapon", ["crossbow"])
        t = texts[0]
        assert "Crossbow" in t
        assert "ranged weapon" in t
        assert "Range 30" in t
        assert "Str 4" in t
        assert "AP 1" in t
        assert "Shots 1" in t
        assert "Armour Bane (1)" in t


# ---------------------------------------------------------------------------
# Army
# ---------------------------------------------------------------------------


class TestArmy:
    def test_name_only(self) -> None:
        driver = _make_driver([[{"nid": "vampire-counts", "name": "Vampire Counts"}]])
        texts = text_builder.build_for_label(driver, "Army", ["vampire-counts"])
        assert texts == ["Vampire Counts"]


# ---------------------------------------------------------------------------
# Unit — most complex builder (3 Cypher queries)
# ---------------------------------------------------------------------------


class TestUnit:
    def _make_driver_for_unit(
        self,
        unit_rec: dict,
        profile_recs: list[dict],
        edge_rec: dict,
    ) -> MagicMock:
        return _make_driver(
            [
                [unit_rec],
                profile_recs,
                [edge_rec],
            ]
        )

    def test_contains_name_and_army(self) -> None:
        driver = self._make_driver_for_unit(
            {
                "nid": "blood-knights",
                "name": "Blood Knights",
                "army_category": "Rare",
                "cost": 39,
                "size_min": 5,
                "size_max": None,
                "bw": 30,
                "bd": 60,
                "av": None,
                "armies": ["Vampire Counts"],
                "troop_types": ["Heavy Cavalry"],
            },
            [
                {
                    "nid": "blood-knights",
                    "pname": "Blood Knight",
                    "M": 8,
                    "WS": 5,
                    "BS": 3,
                    "S": 4,
                    "T": 4,
                    "W": 1,
                    "I": 4,
                    "A": 2,
                    "Ld": 7,
                    "ord": 0,
                }
            ],
            {
                "nid": "blood-knights",
                "rules": ["Fear", "Frenzy"],
                "weapons": ["Lance", "Heavy Armour"],
            },
        )
        texts = text_builder.build_for_label(driver, "Unit", ["blood-knights"])
        t = texts[0]
        assert "Blood Knights" in t
        assert "Vampire Counts" in t
        assert "Heavy Cavalry" in t
        assert "Rare" in t

    def test_contains_cost_and_size(self) -> None:
        driver = self._make_driver_for_unit(
            {
                "nid": "x",
                "name": "X",
                "army_category": None,
                "cost": 10,
                "size_min": 20,
                "size_max": 40,
                "bw": None,
                "bd": None,
                "av": None,
                "armies": [],
                "troop_types": [],
            },
            [],
            {"nid": "x", "rules": [], "weapons": []},
        )
        texts = text_builder.build_for_label(driver, "Unit", ["x"])
        t = texts[0]
        assert "10 pts/model" in t
        assert "Unit size 20-40" in t

    def test_contains_profile_stat_block(self) -> None:
        driver = self._make_driver_for_unit(
            {
                "nid": "blood-knights",
                "name": "Blood Knights",
                "army_category": None,
                "cost": None,
                "size_min": None,
                "size_max": None,
                "bw": None,
                "bd": None,
                "av": None,
                "armies": [],
                "troop_types": [],
            },
            [
                {
                    "nid": "blood-knights",
                    "pname": "Blood Knight",
                    "M": 8,
                    "WS": 5,
                    "BS": 3,
                    "S": 4,
                    "T": 4,
                    "W": 1,
                    "I": 4,
                    "A": 2,
                    "Ld": 7,
                    "ord": 0,
                }
            ],
            {"nid": "blood-knights", "rules": [], "weapons": []},
        )
        texts = text_builder.build_for_label(driver, "Unit", ["blood-knights"])
        t = texts[0]
        assert "Profiles" in t
        assert "Blood Knight" in t
        assert "WS5" in t
        assert "A2" in t

    def test_contains_rules_and_weapons(self) -> None:
        driver = self._make_driver_for_unit(
            {
                "nid": "x",
                "name": "X",
                "army_category": None,
                "cost": None,
                "size_min": None,
                "size_max": None,
                "bw": None,
                "bd": None,
                "av": None,
                "armies": [],
                "troop_types": [],
            },
            [],
            {"nid": "x", "rules": ["Fear", "Frenzy"], "weapons": ["Lance"]},
        )
        texts = text_builder.build_for_label(driver, "Unit", ["x"])
        t = texts[0]
        assert "Fear" in t
        assert "Frenzy" in t
        assert "Lance" in t

    def test_missing_unit_returns_empty(self) -> None:
        driver = _make_driver([[], [], []])
        texts = text_builder.build_for_label(driver, "Unit", ["missing"])
        assert texts == [""]

    def test_contains_upgrades(self) -> None:
        driver = self._make_driver_for_unit(
            {
                "nid": "x",
                "name": "X",
                "army_category": None,
                "cost": None,
                "size_min": None,
                "size_max": None,
                "bw": None,
                "bd": None,
                "av": None,
                "armies": [],
                "troop_types": [],
            },
            [],
            {
                "nid": "x",
                "rules": [],
                "weapons": [],
                "upgrades": ["Magic Item Budget (100 pts)", "Level 2 Wizard"],
            },
        )
        texts = text_builder.build_for_label(driver, "Unit", ["x"])
        t = texts[0]
        assert "Upgrades" in t
        assert "Magic Item Budget (100 pts)" in t
        assert "Level 2 Wizard" in t

    def test_no_upgrades_key_does_not_crash(self) -> None:
        driver = self._make_driver_for_unit(
            {
                "nid": "x",
                "name": "X",
                "army_category": None,
                "cost": None,
                "size_min": None,
                "size_max": None,
                "bw": None,
                "bd": None,
                "av": None,
                "armies": [],
                "troop_types": [],
            },
            [],
            {"nid": "x", "rules": [], "weapons": []},  # no "upgrades" key
        )
        texts = text_builder.build_for_label(driver, "Unit", ["x"])
        assert texts == ["X"]

    def test_empty_upgrade_list_no_segment(self) -> None:
        driver = self._make_driver_for_unit(
            {
                "nid": "x",
                "name": "X",
                "army_category": None,
                "cost": None,
                "size_min": None,
                "size_max": None,
                "bw": None,
                "bd": None,
                "av": None,
                "armies": [],
                "troop_types": [],
            },
            [],
            {"nid": "x", "rules": [], "weapons": [], "upgrades": []},
        )
        texts = text_builder.build_for_label(driver, "Unit", ["x"])
        assert "Upgrades" not in texts[0]
