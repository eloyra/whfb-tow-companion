"""Tests for MagicItemParser.army_id normalisation.

Covers ARCANE_JOURNAL_ASSOCIATION_ARMY_MAP / ARCANE_JOURNAL_PAGE_ARMY_OVERRIDES
resolution, verified against tow.whfb.app (see pipeline/constants.py comments).
"""

from __future__ import annotations

from pipeline.scraper.parsers.magic_item_parser import MagicItemParser


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
