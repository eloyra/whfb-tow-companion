"""
Tests for WeaponParser, SpellParser, and LoreParser helpers and integration.

Uses real raw HTML fixtures from data/raw/ so the tests verify actual wiki markup.
All tests are unit-level: no Neo4j, no network.
"""

from __future__ import annotations

from pathlib import Path

from pipeline.constants import CASTING_VALUE_RULE_ID
from pipeline.scraper.parsers.base_parser import BaseParser
from pipeline.scraper.parsers.lore_parser import LoreParser
from pipeline.scraper.parsers.magic_item_parser import MagicItemParser
from pipeline.scraper.parsers.spell_parser import SpellParser
from pipeline.scraper.parsers.weapon_parser import WeaponParser

_RAW = Path("data/raw")
_FETCHED_AT = "2026-05-01T00:00:00Z"


# ---------------------------------------------------------------------------
# _extract_weapon_profile helper
# ---------------------------------------------------------------------------


# Minimal concrete subclass so we can call the protected method directly.
class _ConcreteParser(BaseParser):
    def parse(self, html, url, fetched_at):  # type: ignore[override]
        raise NotImplementedError


_parser = _ConcreteParser()


def test_extract_weapon_profile_miss_guard_empty_html():
    result = _parser._extract_weapon_profile("")
    assert result == {"range": None, "strength": None, "ap": None, "special_rules": []}


def test_extract_weapon_profile_miss_guard_no_table():
    result = _parser._extract_weapon_profile("<html><body><p>No table here.</p></body></html>")
    assert result == {"range": None, "strength": None, "ap": None, "special_rules": []}


def test_extract_weapon_profile_asrai_longbow():
    html = (_RAW / "weapon" / "asrai-longbow.html").read_text(encoding="utf-8")
    result = _parser._extract_weapon_profile(html)
    assert result["range"] == '32"'
    assert result["strength"] == "S"
    assert result["ap"] is None  # cell is "-"
    assert result["special_rules"] == []


def test_extract_weapon_profile_great_weapon():
    html = (_RAW / "weapon" / "great-weapon.html").read_text(encoding="utf-8")
    result = _parser._extract_weapon_profile(html)
    assert result["range"] == "Combat"
    assert result["strength"] == "S+2"
    assert result["ap"] == "-2"
    assert result["special_rules"] == []


# ---------------------------------------------------------------------------
# WeaponParser integration
# ---------------------------------------------------------------------------

_weapon_parser = WeaponParser()


def test_weapon_parser_asrai_longbow():
    html = (_RAW / "weapon" / "asrai-longbow.html").read_text(encoding="utf-8")
    url = "https://tow.whfb.app/weapons-of-war/asrai-longbow"
    result = _weapon_parser.parse(html, url, _FETCHED_AT)
    assert len(result.nodes) == 1
    node = result.nodes[0]
    assert node["id"] == "asrai-longbow"
    assert node["range"] == '32"'
    assert node["strength"] == "S"
    assert node["ap"] is None
    assert node["special_rules"] == []


def test_weapon_parser_great_weapon():
    html = (_RAW / "weapon" / "great-weapon.html").read_text(encoding="utf-8")
    url = "https://tow.whfb.app/weapons-of-war/great-weapon"
    result = _weapon_parser.parse(html, url, _FETCHED_AT)
    assert len(result.nodes) == 1
    node = result.nodes[0]
    assert node["range"] == "Combat"
    assert node["strength"] == "S+2"
    assert node["ap"] == "-2"


def test_weapon_parser_armour_page_no_table():
    """Armour pages have no profile-table--weapon; fields should stay None."""
    html = (_RAW / "weapon" / "heavy-armour.html").read_text(encoding="utf-8")
    url = "https://tow.whfb.app/weapons-of-war/heavy-armour"
    result = _weapon_parser.parse(html, url, _FETCHED_AT)
    assert len(result.nodes) == 1
    node = result.nodes[0]
    assert node["range"] is None
    assert node["strength"] is None
    assert node["ap"] is None


# ---------------------------------------------------------------------------
# _extract_spell_type helper (dedicated-page variant)
# ---------------------------------------------------------------------------


def test_extract_spell_type_miss_guard_empty_html():
    assert _parser._extract_spell_type("") is None


def test_extract_spell_type_oaken_shield():
    html = (_RAW / "core_rule" / "oaken-shield.html").read_text(encoding="utf-8")
    result = _parser._extract_spell_type(html)
    assert result == "Enchantment"


# ---------------------------------------------------------------------------
# SpellParser integration (dedicated /spell/{slug} pages)
# ---------------------------------------------------------------------------

_spell_parser = SpellParser()


def test_spell_parser_oaken_shield_structured_fields():
    """Dedicated spell page should yield structured casting_value, range, spell_type."""
    html = (_RAW / "core_rule" / "oaken-shield.html").read_text(encoding="utf-8")
    url = "https://tow.whfb.app/spell/oaken-shield"
    result = _spell_parser.parse(html, url, _FETCHED_AT)
    assert len(result.nodes) == 1
    node = result.nodes[0]
    assert node["id"] == "oaken-shield"
    assert node["casting_value"] == 7
    assert node["range"] == "Self"
    assert node["spell_type"] == "Enchantment"
    assert "5+" in (node["text"] or "")


def test_spell_parser_oaken_shield_references_edges():
    """oaken-shield should link enchantment, range-self-spells, start-of-turn, ward-saves,
    and the casting-value rule."""
    html = (_RAW / "core_rule" / "oaken-shield.html").read_text(encoding="utf-8")
    url = "https://tow.whfb.app/spell/oaken-shield"
    result = _spell_parser.parse(html, url, _FETCHED_AT)
    ref_targets = {e["dst"] for e in result.edges if e["relation"] == "REFERENCES"}
    assert "enchantment" in ref_targets
    assert "range-self-spells" in ref_targets
    assert "start-of-turn" in ref_targets
    assert "ward-saves" in ref_targets
    assert CASTING_VALUE_RULE_ID in ref_targets


def test_spell_parser_renegade_spell_structured():
    """Renegade-lore dedicated page should still yield structured fields, no crash."""
    html = (_RAW / "core_rule" / "plague-wind.html").read_text(encoding="utf-8")
    url = "https://tow.whfb.app/spell/plague-wind"
    result = _spell_parser.parse(html, url, _FETCHED_AT)
    assert len(result.nodes) == 1
    node = result.nodes[0]
    assert node["casting_value"] == 7
    assert node["range"] is not None
    ref_targets = {e["dst"] for e in result.edges if e["relation"] == "REFERENCES"}
    assert CASTING_VALUE_RULE_ID in ref_targets


# ---------------------------------------------------------------------------
# LoreParser integration
# ---------------------------------------------------------------------------

_lore_parser = LoreParser()


def test_lore_parser_emits_lore_node_no_spell_nodes():
    """LoreParser should emit exactly one Lore node and no Spell nodes."""
    html = (_RAW / "spell" / "battle-magic.html").read_text(encoding="utf-8")
    url = "https://tow.whfb.app/the-lores-of-magic/battle-magic"
    result = _lore_parser.parse(html, url, _FETCHED_AT)
    lore_nodes = [n for n in result.nodes if n.get("node_type") == "lore"]
    spell_nodes = [n for n in result.nodes if n.get("node_type") == "spell"]
    assert len(lore_nodes) == 1
    assert lore_nodes[0]["id"] == "battle-magic"
    assert spell_nodes == []


def test_lore_parser_emits_belongs_to_lore_edges():
    """Standard lore page should emit BELONGS_TO_LORE edges for all embedded spells."""
    html = (_RAW / "spell" / "battle-magic.html").read_text(encoding="utf-8")
    url = "https://tow.whfb.app/the-lores-of-magic/battle-magic"
    result = _lore_parser.parse(html, url, _FETCHED_AT)
    btl_edges = [e for e in result.edges if e["relation"] == "BELONGS_TO_LORE"]
    assert len(btl_edges) > 0
    slug_set = {e["src"] for e in btl_edges}
    assert "oaken-shield" in slug_set
    assert "hammerhand" in slug_set


# ---------------------------------------------------------------------------
# MagicItemParser integration (dedicated /magic-item/{slug} pages)
#
# The manifest labels these pages "core_rule" (same bug class as the /spell/
# collision fixed in ADR-0006 — no dedicated page_type bucket exists for the
# singular URL). Before the parsers/__init__.py routing override, every one
# of these ~700 cached pages was parsed by CoreRuleParser instead, producing
# a same-id CoreRule node for every MagicItem.
# ---------------------------------------------------------------------------

_magic_item_parser = MagicItemParser()


def test_magic_item_parser_dedicated_page_ogre_blade():
    """A real cached dedicated magic-item page should yield one MagicItem node."""
    html = (_RAW / "core_rule" / "ogre-blade.html").read_text(encoding="utf-8")
    url = "https://tow.whfb.app/magic-item/ogre-blade"
    result = _magic_item_parser.parse(html, url, _FETCHED_AT)
    assert len(result.nodes) == 1
    node = result.nodes[0]
    assert node["node_type"] == "magic_item"
    assert node["id"] == "ogre-blade"
    assert node["name"] == "Ogre Blade"
    assert node["points_cost"] == 75
