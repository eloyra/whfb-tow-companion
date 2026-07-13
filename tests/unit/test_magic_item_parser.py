"""Tests for MagicItemParser.army_id normalisation and page-shape routing.

Covers ARCANE_JOURNAL_ASSOCIATION_ARMY_MAP / ARCANE_JOURNAL_PAGE_ARMY_OVERRIDES
resolution, verified against tow.whfb.app (see pipeline/constants.py comments).
"""

from __future__ import annotations

import json

from pipeline.scraper.parsers.magic_item_parser import MagicItemParser


def _html_with_next_data(entry: dict) -> str:
    payload = json.dumps({"props": {"pageProps": {"entry": entry}}})
    return f'<script id="__NEXT_DATA__" type="application/json">{payload}</script>'


class TestNormalizeArmyId:
    def setup_method(self) -> None:
        self.parser = MagicItemParser()

    def test_none_passes_through(self) -> None:
        assert self.parser._normalize_army_id(None, "https://tow.whfb.app/magic-items/x") is None

    def test_plain_army_slug_unchanged(self) -> None:
        result = self.parser._normalize_army_id(
            "vampire-counts", "https://tow.whfb.app/magic-items/vampiric-powers"
        )
        assert result == "vampire-counts"

    def test_arcane_journal_association_maps_to_army(self) -> None:
        result = self.parser._normalize_army_id(
            "arcane-journal-dwarfen-mountain-holds",
            "https://tow.whfb.app/magic-items/runes-of-battle",
        )
        assert result == "dwarfen-mountain-holds"

    def test_page_override_takes_priority_over_association(self) -> None:
        # "The War of Settra's Fury" covers multiple armies; the
        # incantations-scrolls page is specifically Tomb Kings.
        result = self.parser._normalize_army_id(
            "arcane-journal-the-war-of-settras-fury",
            "https://tow.whfb.app/magic-items/incantations-scrolls",
        )
        assert result == "tomb-kings-of-khemri"

    def test_unmapped_page_in_ambiguous_book_keeps_raw_slug(self) -> None:
        # "infamous-origins" is a niche Army-of-Infamy muster list with no
        # corresponding :Army node — intentionally left unmapped.
        result = self.parser._normalize_army_id(
            "arcane-journal-the-war-of-settras-fury",
            "https://tow.whfb.app/magic-items/infamous-origins",
        )
        assert result == "arcane-journal-the-war-of-settras-fury"

    def test_unmapped_arcane_journal_slug_keeps_raw_slug(self) -> None:
        result = self.parser._normalize_army_id(
            "arcane-journal-some-future-book",
            "https://tow.whfb.app/magic-items/some-future-page",
        )
        assert result == "arcane-journal-some-future-book"


class TestDedicatedItemPage:
    """A dedicated ``/magic-item/{slug}`` page's own Contentful entry (content
    type ``magicItem``) is one item's data directly on ``entry.fields`` — not
    a list page's embedded-block body. Manifest labels these pages
    ``core_rule``; before the ``parsers/__init__.py`` routing override, they
    produced a same-id ``CoreRule`` node for every ``MagicItem`` (same bug
    class as the ``/spell/`` collision fixed in ADR-0006).
    """

    def setup_method(self) -> None:
        self.parser = MagicItemParser()

    def _entry(self, **field_overrides: object) -> dict:
        fields = {
            "name": "Ogre Blade",
            "slug": "ogre-blade",
            "type": "Magic Weapon",
            "cost": 75,
            "costOverride": None,
            "description": {"nodeType": "document", "content": [], "data": {}},
            "body": {"nodeType": "document", "content": [], "data": {}},
            "association": [
                {"fields": {"slug": "rulebook", "name": "Rulebook"}},
            ],
        }
        fields.update(field_overrides)
        return {"sys": {"contentType": {"sys": {"id": "magicItem"}}}, "fields": fields}

    def test_parses_one_item_directly_from_entry_fields(self) -> None:
        html = _html_with_next_data(self._entry())
        result = self.parser.parse(
            html, "https://tow.whfb.app/magic-item/ogre-blade", "2026-01-01T00:00:00Z"
        )
        assert len(result.nodes) == 1
        node = result.nodes[0]
        assert node["id"] == "ogre-blade"
        assert node["name"] == "Ogre Blade"
        assert node["points_cost"] == 75
        assert node["army_id"] is None  # generic rulebook association

    def test_army_specific_item_resolves_army_id(self) -> None:
        html = _html_with_next_data(
            self._entry(
                name="Vampiric Power",
                slug="vampiric-power",
                association=[{"fields": {"slug": "vampire-counts", "name": "Vampire Counts"}}],
            )
        )
        result = self.parser.parse(
            html, "https://tow.whfb.app/magic-item/vampiric-power", "2026-01-01T00:00:00Z"
        )
        assert result.nodes[0]["army_id"] == "vampire-counts"

    def test_list_page_shape_unaffected(self) -> None:
        # content type "rule" (list page) must still take the embedded-block path.
        entry = {
            "sys": {"contentType": {"sys": {"id": "rule"}}},
            "fields": {
                "name": "Magic Weapons",
                "association": [{"fields": {"slug": "rulebook", "name": "Rulebook"}}],
                "body": {
                    "nodeType": "document",
                    "data": {},
                    "content": [
                        {
                            "nodeType": "embedded-entry-block",
                            "data": {
                                "magicItem": [
                                    {
                                        "fields": {
                                            "name": "Sword of Sorrow",
                                            "slug": "sword-of-sorrow",
                                            "type": "Magic Weapon",
                                            "cost": 50,
                                            "description": {
                                                "nodeType": "document",
                                                "content": [],
                                                "data": {},
                                            },
                                            "body": {
                                                "nodeType": "document",
                                                "content": [],
                                                "data": {},
                                            },
                                        }
                                    }
                                ]
                            },
                        }
                    ],
                },
            },
        }
        html = _html_with_next_data(entry)
        result = self.parser.parse(
            html, "https://tow.whfb.app/magic-items/magic-weapons", "2026-01-01T00:00:00Z"
        )
        assert len(result.nodes) == 1
        assert result.nodes[0]["id"] == "sword-of-sorrow"
