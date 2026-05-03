"""
Tests for ArmyListParser: BSB extraction, allies parsing, slot section,
legacy army slug stripping, and absent-section handling.
"""

from __future__ import annotations

import json

import pytest

from pipeline.scraper.parsers.army_list_parser import ArmyListParser

_PARSER = ArmyListParser()

_HTML_TEMPLATE = """<html><head></head><body>
<script id="__NEXT_DATA__" type="application/json">{next_data}</script>
</body></html>"""


# ---------------------------------------------------------------------------
# Rich-text fixture helpers
# ---------------------------------------------------------------------------


def _text(value: str) -> dict:
    return {"nodeType": "text", "value": value}


def _para(*children: dict) -> dict:
    return {"nodeType": "paragraph", "content": list(children)}


def _h3(value: str) -> dict:
    return {"nodeType": "heading-3", "content": [_text(value)]}


def _hyperlink(slug: str, ct: str, display: str = "") -> dict:
    return {
        "nodeType": "entry-hyperlink",
        "data": {
            "target": {
                "fields": {"slug": slug},
                "sys": {"contentType": {"sys": {"id": ct}}},
            }
        },
        "content": [_text(display or slug)],
    }


def _list_item(*children: dict) -> dict:
    return {"nodeType": "list-item", "content": list(children)}


def _ulist(*items: dict) -> dict:
    return {"nodeType": "unordered-list", "content": list(items)}


def _make_html(army_slug: str, sections: dict[str, list[dict]]) -> str:
    content: list[dict] = []
    for name, nodes in sections.items():
        content.append(_h3(name))
        content.extend(nodes)
    entry = {
        "fields": {
            "slug": f"{army_slug}-army-list",
            "body": {"nodeType": "document", "content": content},
        }
    }
    next_data = json.dumps(
        {"props": {"pageProps": {"entry": entry}}, "isFallback": False}
    )
    return _HTML_TEMPLATE.format(next_data=next_data)


# ---------------------------------------------------------------------------
# BSB section — Empire (text-only, regex path)
# ---------------------------------------------------------------------------


class TestBSBExtraction:
    _URL = "https://tow.whfb.app/warhammer-armies/empire-of-man-army-list"

    def _make_html(self) -> str:
        bsb_para = _para(
            _text(
                "A single Captain of the Empire in your army may be upgraded to"
                " Battle Standard Bearer (+25 points)."
                " He may carry a magic standard with no points limit."
            )
        )
        return _make_html("empire-of-man", {"Battle Standard Bearer": [bsb_para]})

    def test_bsb_upgrade_node_emitted(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        bsb = [n for n in result.nodes if n.get("upgrade_type") == "command_bsb"]
        assert len(bsb) == 1

    def test_bsb_character_slug_from_text(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        bsb = [n for n in result.nodes if n.get("upgrade_type") == "command_bsb"][0]
        assert bsb["id"].startswith("captain-of-the-empire#upgrade-bsb-")

    def test_bsb_army_slug_in_id(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        bsb = [n for n in result.nodes if n.get("upgrade_type") == "command_bsb"][0]
        assert "empire-of-man" in bsb["id"]

    def test_bsb_points_cost(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        bsb = [n for n in result.nodes if n.get("upgrade_type") == "command_bsb"][0]
        assert bsb["points_cost"] == 25

    def test_bsb_unlimited_magic_standard_true(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        bsb = [n for n in result.nodes if n.get("upgrade_type") == "command_bsb"][0]
        assert bsb["bsb_unlimited_magic_standard"] is True

    def test_has_upgrade_edge_from_character(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        has_upgrade = [e for e in result.edges if e["relation"] == "HAS_UPGRADE"]
        assert len(has_upgrade) == 1
        assert has_upgrade[0]["src"] == "captain-of-the-empire"

    def test_bsb_via_armylistentry_hyperlink(self) -> None:
        bsb_para = _para(
            _text("A single "),
            _hyperlink("lord-of-the-empire", "armyListEntry", "Lord of the Empire"),
            _text(" in your army may be upgraded to Battle Standard Bearer (+25 points)."),
        )
        html = _make_html("empire-of-man", {"Battle Standard Bearer": [bsb_para]})
        result = _PARSER.parse(html, self._URL, "2024-01-01")
        bsb = [n for n in result.nodes if n.get("upgrade_type") == "command_bsb"]
        assert len(bsb) == 1
        assert bsb[0]["id"].startswith("lord-of-the-empire#upgrade-bsb-")


# ---------------------------------------------------------------------------
# BSB — limited magic standard
# ---------------------------------------------------------------------------


class TestBSBLimitedMagicStandard:
    _URL = "https://tow.whfb.app/warhammer-armies/dark-elves-army-list"

    def test_bsb_limited_magic_standard_false(self) -> None:
        bsb_para = _para(
            _text(
                "A single Dreadlord in your army may be upgraded to"
                " Battle Standard Bearer (+25 points)."
                " He may carry a magic standard worth up to 50 points."
            )
        )
        html = _make_html("dark-elves", {"Battle Standard Bearer": [bsb_para]})
        result = _PARSER.parse(html, self._URL, "2024-01-01")
        bsb = [n for n in result.nodes if n.get("upgrade_type") == "command_bsb"][0]
        assert bsb["bsb_unlimited_magic_standard"] is False


# ---------------------------------------------------------------------------
# Allies section — Vampire Counts
# ---------------------------------------------------------------------------


class TestAlliesExtraction:
    _URL = "https://tow.whfb.app/warhammer-armies/vampire-counts-army-list"

    def _make_html(self) -> str:
        allies_list = _ulist(
            _list_item(_para(
                _text("Dwarfen Mountain Holds (trusted) "),
                _hyperlink("dwarfen-mountain-holds", "association"),
            )),
            _list_item(_para(
                _text("Grand Cathay (suspicious) "),
                _hyperlink("grand-cathay-army-list", "rule"),
            )),
            _list_item(_para(
                _text("Kingdom of Bretonnia "),  # no alliance type → defaults to "trusted"
                _hyperlink("kingdom-of-bretonnia", "association"),
            )),
        )
        return _make_html("vampire-counts", {"Allies": [allies_list]})

    def test_allied_with_count(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        allied = [e for e in result.edges if e["relation"] == "ALLIED_WITH"]
        assert len(allied) == 3

    def test_alliance_type_trusted(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        by_dst = {e["dst"]: e for e in result.edges if e["relation"] == "ALLIED_WITH"}
        assert by_dst["dwarfen-mountain-holds"]["properties"]["alliance_type"] == "trusted"

    def test_alliance_type_suspicious(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        by_dst = {e["dst"]: e for e in result.edges if e["relation"] == "ALLIED_WITH"}
        assert by_dst["grand-cathay"]["properties"]["alliance_type"] == "suspicious"

    def test_army_list_suffix_stripped_from_rule_type(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        dst_ids = {e["dst"] for e in result.edges if e["relation"] == "ALLIED_WITH"}
        assert "grand-cathay" in dst_ids
        assert "grand-cathay-army-list" not in dst_ids

    def test_no_alliance_type_defaults_to_trusted(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        by_dst = {e["dst"]: e for e in result.edges if e["relation"] == "ALLIED_WITH"}
        assert by_dst["kingdom-of-bretonnia"]["properties"]["alliance_type"] == "trusted"

    def test_allied_with_src_is_army_slug(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        allied = [e for e in result.edges if e["relation"] == "ALLIED_WITH"]
        assert all(e["src"] == "vampire-counts" for e in allied)

    def test_army_does_not_ally_with_itself(self) -> None:
        # An ally that happens to share the army slug should be silently dropped
        allies_list = _ulist(
            _list_item(_para(
                _text("Vampire Counts "),
                _hyperlink("vampire-counts", "association"),
            )),
        )
        html = _make_html("vampire-counts", {"Allies": [allies_list]})
        result = _PARSER.parse(html, self._URL, "2024-01-01")
        allied = [e for e in result.edges if e["relation"] == "ALLIED_WITH"]
        assert allied == []


# ---------------------------------------------------------------------------
# Slot section — CompositionList + CompositionSlot
# ---------------------------------------------------------------------------


class TestCompositionSlot:
    _URL = "https://tow.whfb.app/warhammer-armies/vampire-counts-army-list"

    def _make_html(self) -> str:
        slot_items = _ulist(
            _list_item(_para(_hyperlink("skeleton-warriors", "armyListEntry", "Skeleton Warriors"))),
            _list_item(_para(_hyperlink("crypt-ghouls", "armyListEntry", "Crypt Ghouls"))),
        )
        return _make_html("vampire-counts", {
            "Core": [
                _para(_text("Up to 50% of your army's points may be spent on Core units.")),
                slot_items,
            ]
        })

    def test_composition_list_node(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        comp_lists = [n for n in result.nodes if n.get("node_type") == "composition_list"]
        assert len(comp_lists) == 1
        assert comp_lists[0]["army_id"] == "vampire-counts"

    def test_composition_slot_node(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        slots = [n for n in result.nodes if n.get("node_type") == "composition_slot"]
        assert len(slots) == 1
        assert slots[0]["slot_name"] == "Core"

    def test_slot_max_pct_parsed(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        slot = next(n for n in result.nodes if n.get("node_type") == "composition_slot")
        assert slot["max_pct"] == 50

    def test_slot_min_pct_absent(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        slot = next(n for n in result.nodes if n.get("node_type") == "composition_slot")
        assert slot["min_pct"] is None

    def test_slot_allows_edges(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        allows = [e for e in result.edges if e["relation"] == "SLOT_ALLOWS"]
        dst_ids = {e["dst"] for e in allows}
        assert {"skeleton-warriors", "crypt-ghouls"} == dst_ids

    def test_has_list_edge(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        has_list = [e for e in result.edges if e["relation"] == "HAS_LIST"]
        assert len(has_list) == 1
        assert has_list[0]["src"] == "vampire-counts"

    def test_has_slot_edge(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        has_slot = [e for e in result.edges if e["relation"] == "HAS_SLOT"]
        assert len(has_slot) == 1

    def test_at_least_pct(self) -> None:
        slot_items = _ulist(
            _list_item(_para(_hyperlink("state-troops", "armyListEntry", "State Troops"))),
        )
        html = _make_html("empire-of-man", {
            "Core": [
                _para(_text("At least 25% of your army's points must be spent on Core units.")),
                slot_items,
            ]
        })
        result = _PARSER.parse(
            html,
            "https://tow.whfb.app/warhammer-armies/empire-of-man-army-list",
            "2024-01-01",
        )
        slot = next(n for n in result.nodes if n.get("node_type") == "composition_slot")
        assert slot["min_pct"] == 25
        assert slot["max_pct"] is None


# ---------------------------------------------------------------------------
# Daemons of Chaos (legacy) — no Allies, no Mercenaries
# ---------------------------------------------------------------------------


class TestDaemonsNoAllies:
    _URL = "https://tow.whfb.app/warhammer-armies/daemons-of-chaos-legacy-army-list"

    def _make_html(self) -> str:
        slot_para = _para(_text("Up to 25% of your army's points."))
        slot_items = _ulist(
            _list_item(_para(_hyperlink("bloodletters", "armyListEntry", "Bloodletters")))
        )
        return _make_html("daemons-of-chaos-legacy", {
            "Characters": [slot_para, slot_items],
            "Core": [slot_para, slot_items],
            "Special": [slot_para, slot_items],
            "Rare": [slot_para, slot_items],
        })

    def test_no_allied_with_edges(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        allied = [e for e in result.edges if e["relation"] == "ALLIED_WITH"]
        assert allied == []

    def test_four_slots_only(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        slots = [n for n in result.nodes if n.get("node_type") == "composition_slot"]
        assert len(slots) == 4

    def test_slot_names_are_canonical(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        slot_names = {n["slot_name"] for n in result.nodes if n.get("node_type") == "composition_slot"}
        assert slot_names == {"Characters", "Core", "Special", "Rare"}

    def test_legacy_slug_produces_base_army_id(self) -> None:
        result = _PARSER.parse(self._make_html(), self._URL, "2024-01-01")
        comp_lists = [n for n in result.nodes if n.get("node_type") == "composition_list"]
        assert comp_lists[0]["army_id"] == "daemons-of-chaos"


# ---------------------------------------------------------------------------
# Empty / missing sections
# ---------------------------------------------------------------------------


class TestMissingSections:
    def test_missing_body_returns_empty_result(self) -> None:
        entry = {"fields": {"slug": "empire-of-man-army-list"}}
        next_data = json.dumps(
            {"props": {"pageProps": {"entry": entry}}, "isFallback": False}
        )
        html = _HTML_TEMPLATE.format(next_data=next_data)
        result = _PARSER.parse(
            html,
            "https://tow.whfb.app/warhammer-armies/empire-of-man-army-list",
            "2024-01-01",
        )
        assert result.nodes == []
        assert result.edges == []

    def test_no_bsb_section_emits_no_bsb_upgrade(self) -> None:
        html = _make_html("empire-of-man", {
            "Core": [_para(_text("Up to 50% of your points."))]
        })
        result = _PARSER.parse(
            html,
            "https://tow.whfb.app/warhammer-armies/empire-of-man-army-list",
            "2024-01-01",
        )
        bsb = [n for n in result.nodes if n.get("upgrade_type") == "command_bsb"]
        assert bsb == []
