"""
Tests for parse-time property flattening.

Verifies that BaseParser helpers produce flat node dicts (no nested maps)
and that UnitParser emits :Profile child nodes + HAS_PROFILE edges.
"""

from __future__ import annotations

import json

import pytest

from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult
from pipeline.scraper.parsers.unit_parser import UnitParser

# ---------------------------------------------------------------------------
# Minimal concrete BaseParser for testing helpers
# ---------------------------------------------------------------------------


class _StubParser(BaseParser):
    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        return ParseResult()


@pytest.fixture()
def stub() -> _StubParser:
    return _StubParser()


# ---------------------------------------------------------------------------
# _make_source_citation
# ---------------------------------------------------------------------------


class TestMakeSourceCitation:
    def test_flat_keys(self, stub: _StubParser) -> None:
        result = stub._make_source_citation("Vampire Counts", 42)
        assert result == {"source_citation_book": "Vampire Counts", "source_citation_page": 42}
        assert "source_citation" not in result

    def test_no_page(self, stub: _StubParser) -> None:
        result = stub._make_source_citation("Core Rules")
        assert result["source_citation_page"] is None

    def test_spreadable(self, stub: _StubParser) -> None:
        node: dict = {"id": "test", **stub._make_source_citation("Book", 1)}
        assert node["source_citation_book"] == "Book"
        assert node["source_citation_page"] == 1


# ---------------------------------------------------------------------------
# _make_i18n
# ---------------------------------------------------------------------------


class TestMakeI18n:
    def test_returns_empty(self, stub: _StubParser) -> None:
        result = stub._make_i18n(name="Vampire Count", text="Some text")
        assert result == {}

    def test_no_raw_i18n_key(self, stub: _StubParser) -> None:
        result = stub._make_i18n(name="X")
        assert "i18n" not in result


# ---------------------------------------------------------------------------
# _parse_base_size
# ---------------------------------------------------------------------------


class TestParseBaseSize:
    @pytest.mark.parametrize(
        "raw, width, depth",
        [
            ("30 x 60 mm", 30, 60),
            ("25x25mm", 25, 25),
            ("20 X 20", 20, 20),
            ("50×50mm", 50, 50),
        ],
    )
    def test_parses_valid(self, stub: _StubParser, raw: str, width: int, depth: int) -> None:
        result = stub._parse_base_size(raw)
        assert result == {"base_width_mm": width, "base_depth_mm": depth}

    def test_empty_string(self, stub: _StubParser) -> None:
        result = stub._parse_base_size("")
        assert result == {"base_width_mm": None, "base_depth_mm": None}

    def test_no_nested_dict(self, stub: _StubParser) -> None:
        result = stub._parse_base_size("30 x 60 mm")
        for v in result.values():
            assert not isinstance(v, dict)


# ---------------------------------------------------------------------------
# _parse_unit_size
# ---------------------------------------------------------------------------


class TestParseUnitSize:
    @pytest.mark.parametrize(
        "raw, min_, max_",
        [
            ("5+", 5, None),
            ("20-40", 20, 40),
            ("20–40", 20, 40),
            ("1", 1, 1),
            ("10", 10, 10),
        ],
    )
    def test_parses_valid(self, stub: _StubParser, raw: str, min_: int, max_: int | None) -> None:
        result = stub._parse_unit_size(raw)
        assert result == {"unit_size_min": min_, "unit_size_max": max_}

    def test_no_nested_dict(self, stub: _StubParser) -> None:
        result = stub._parse_unit_size("5+")
        for v in result.values():
            assert not isinstance(v, dict)


# ---------------------------------------------------------------------------
# UnitParser emits flat nodes + :Profile children
# ---------------------------------------------------------------------------

_UNIT_HTML_TEMPLATE = """
<html><head></head><body>
<script id="__NEXT_DATA__" type="application/json">
{next_data}
</script>
</body></html>
"""


def _make_unit_next_data(
    slug: str,
    name: str,
    army_slug: str,
    army_name: str,
    profiles: list[dict],
    unit_size: str = "5+",
    base_size: str = "30 x 60 mm",
) -> str:
    entry = {
        "sys": {"contentType": {"sys": {"id": "armyListEntry"}}},
        "fields": {
            "slug": slug,
            "name": name,
            "unitProfile": [
                {
                    "Name": p["name"],
                    "M": str(p.get("M", "-")),
                    "WS": str(p.get("WS", "-")),
                    "BS": str(p.get("BS", "-")),
                    "S": str(p.get("S", "-")),
                    "T": str(p.get("T", "-")),
                    "W": str(p.get("W", "-")),
                    "I": str(p.get("I", "-")),
                    "A": str(p.get("A", "-")),
                    "Ld": str(p.get("Ld", "-")),
                }
                for p in profiles
            ],
            "association": [
                {
                    "fields": {"slug": army_slug, "name": army_name},
                    "sys": {"contentType": {"sys": {"id": "army"}}},
                }
            ],
            "unitSize": unit_size,
            "baseSize": base_size,
        },
    }
    return json.dumps({"props": {"pageProps": {"entry": entry}}, "isFallback": False})


class TestUnitParserFlattening:
    def test_no_source_citation_dict(self) -> None:
        html = _UNIT_HTML_TEMPLATE.format(
            next_data=_make_unit_next_data(
                "blood-knights",
                "Blood Knights",
                "vampire-counts",
                "Vampire Counts",
                [
                    {
                        "name": "Blood Knight",
                        "M": 8,
                        "WS": 5,
                        "BS": 3,
                        "S": 4,
                        "T": 4,
                        "W": 1,
                        "I": 4,
                        "A": 2,
                        "Ld": 7,
                    }
                ],
            )
        )
        result = UnitParser().parse(
            html, "https://tow.whfb.app/unit/blood-knights", "2024-01-01T00:00:00Z"
        )
        unit_nodes = [n for n in result.nodes if n.get("node_type") == "unit"]
        assert unit_nodes, "No unit node emitted"
        unit = unit_nodes[0]
        assert "source_citation" not in unit
        assert "source_citation_book" in unit
        assert "source_citation_page" in unit

    def test_no_base_size_dict(self) -> None:
        html = _UNIT_HTML_TEMPLATE.format(
            next_data=_make_unit_next_data(
                "blood-knights",
                "Blood Knights",
                "vampire-counts",
                "Vampire Counts",
                [{"name": "Blood Knight", "M": 8, "WS": 5}],
                base_size="30 x 60 mm",
            )
        )
        result = UnitParser().parse(
            html, "https://tow.whfb.app/unit/blood-knights", "2024-01-01T00:00:00Z"
        )
        unit = next(n for n in result.nodes if n.get("node_type") == "unit")
        assert "base_size_mm" not in unit
        assert unit.get("base_width_mm") == 30
        assert unit.get("base_depth_mm") == 60

    def test_no_unit_size_dict(self) -> None:
        html = _UNIT_HTML_TEMPLATE.format(
            next_data=_make_unit_next_data(
                "blood-knights",
                "Blood Knights",
                "vampire-counts",
                "Vampire Counts",
                [{"name": "Blood Knight", "M": 8}],
                unit_size="5+",
            )
        )
        result = UnitParser().parse(
            html, "https://tow.whfb.app/unit/blood-knights", "2024-01-01T00:00:00Z"
        )
        unit = next(n for n in result.nodes if n.get("node_type") == "unit")
        assert "unit_size" not in unit
        assert unit.get("unit_size_min") == 5
        assert unit.get("unit_size_max") is None

    def test_no_i18n_dict(self) -> None:
        html = _UNIT_HTML_TEMPLATE.format(
            next_data=_make_unit_next_data(
                "blood-knights",
                "Blood Knights",
                "vampire-counts",
                "Vampire Counts",
                [{"name": "Blood Knight", "M": 8}],
            )
        )
        result = UnitParser().parse(
            html, "https://tow.whfb.app/unit/blood-knights", "2024-01-01T00:00:00Z"
        )
        unit = next(n for n in result.nodes if n.get("node_type") == "unit")
        assert "i18n" not in unit

    def test_profiles_emitted_as_separate_nodes(self) -> None:
        profiles_input = [
            {
                "name": "Blood Knight",
                "M": 8,
                "WS": 5,
                "BS": 3,
                "S": 4,
                "T": 4,
                "W": 1,
                "I": 4,
                "A": 2,
                "Ld": 7,
            },
            {
                "name": "Kastellan",
                "M": 8,
                "WS": 5,
                "BS": 3,
                "S": 4,
                "T": 4,
                "W": 2,
                "I": 4,
                "A": 3,
                "Ld": 8,
            },
        ]
        html = _UNIT_HTML_TEMPLATE.format(
            next_data=_make_unit_next_data(
                "blood-knights",
                "Blood Knights",
                "vampire-counts",
                "Vampire Counts",
                profiles_input,
            )
        )
        result = UnitParser().parse(
            html, "https://tow.whfb.app/unit/blood-knights", "2024-01-01T00:00:00Z"
        )
        profile_nodes = [n for n in result.nodes if n.get("node_type") == "profile"]
        assert len(profile_nodes) == 2

    def test_profiles_not_in_unit_node(self) -> None:
        html = _UNIT_HTML_TEMPLATE.format(
            next_data=_make_unit_next_data(
                "blood-knights",
                "Blood Knights",
                "vampire-counts",
                "Vampire Counts",
                [{"name": "Blood Knight", "M": 8}],
            )
        )
        result = UnitParser().parse(
            html, "https://tow.whfb.app/unit/blood-knights", "2024-01-01T00:00:00Z"
        )
        unit = next(n for n in result.nodes if n.get("node_type") == "unit")
        assert "profiles" not in unit

    def test_has_profile_edges_emitted(self) -> None:
        profiles_input = [
            {"name": "Blood Knight", "M": 8, "WS": 5},
            {"name": "Kastellan", "M": 8, "WS": 5},
        ]
        html = _UNIT_HTML_TEMPLATE.format(
            next_data=_make_unit_next_data(
                "blood-knights",
                "Blood Knights",
                "vampire-counts",
                "Vampire Counts",
                profiles_input,
            )
        )
        result = UnitParser().parse(
            html, "https://tow.whfb.app/unit/blood-knights", "2024-01-01T00:00:00Z"
        )
        has_profile_edges = [e for e in result.edges if e["relation"] == "HAS_PROFILE"]
        assert len(has_profile_edges) == 2

    def test_profile_order_property(self) -> None:
        profiles_input = [
            {"name": "Blood Knight", "M": 8},
            {"name": "Kastellan", "M": 8},
        ]
        html = _UNIT_HTML_TEMPLATE.format(
            next_data=_make_unit_next_data(
                "blood-knights",
                "Blood Knights",
                "vampire-counts",
                "Vampire Counts",
                profiles_input,
            )
        )
        result = UnitParser().parse(
            html, "https://tow.whfb.app/unit/blood-knights", "2024-01-01T00:00:00Z"
        )
        profile_nodes = sorted(
            [n for n in result.nodes if n.get("node_type") == "profile"],
            key=lambda n: n["order"],
        )
        assert profile_nodes[0]["order"] == 0
        assert profile_nodes[1]["order"] == 1

    def test_profile_edge_src_is_unit(self) -> None:
        html = _UNIT_HTML_TEMPLATE.format(
            next_data=_make_unit_next_data(
                "blood-knights",
                "Blood Knights",
                "vampire-counts",
                "Vampire Counts",
                [{"name": "Blood Knight", "M": 8}],
            )
        )
        result = UnitParser().parse(
            html, "https://tow.whfb.app/unit/blood-knights", "2024-01-01T00:00:00Z"
        )
        edge = next(e for e in result.edges if e["relation"] == "HAS_PROFILE")
        assert edge["src"] == "blood-knights"
        assert edge["dst"].startswith("blood-knights#")

    def test_profile_has_stat_fields(self) -> None:
        html = _UNIT_HTML_TEMPLATE.format(
            next_data=_make_unit_next_data(
                "blood-knights",
                "Blood Knights",
                "vampire-counts",
                "Vampire Counts",
                [{"name": "Blood Knight", "M": 8, "WS": 5, "A": 2}],
            )
        )
        result = UnitParser().parse(
            html, "https://tow.whfb.app/unit/blood-knights", "2024-01-01T00:00:00Z"
        )
        profile = next(n for n in result.nodes if n.get("node_type") == "profile")
        assert profile["M"] == 8
        assert profile["WS"] == 5
        assert profile["A"] == 2
