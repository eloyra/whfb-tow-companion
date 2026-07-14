"""Tests for UnitParser.

Uses real raw HTML fixtures from data/samples/ so the tests verify actual wiki markup.
All tests are unit-level: no Neo4j, no network.
"""

from __future__ import annotations

from pathlib import Path

from pipeline.scraper.parsers.unit_parser import UnitParser

_RAW = Path("data/samples")
_FETCHED_AT = "2026-05-01T00:00:00Z"

_parser = UnitParser()


def _unit_node(result):
    return next(n for n in result.nodes if n.get("node_type") == "unit")


def test_wizard_level_parsed_as_int():
    """Contentful stores wizardLevel as a numeric string ("3"); the parsed node
    must hold a real int so downstream Cypher numeric comparisons
    (`u.wizard_level >= 1`, used for arcane-item eligibility) work."""
    html = (_RAW / "unit" / "archmage.html").read_text(encoding="utf-8")
    url = "https://tow.whfb.app/unit/archmage"
    result = _parser.parse(html, url, _FETCHED_AT)
    node = _unit_node(result)
    assert isinstance(node["wizard_level"], int)
    assert node["wizard_level"] >= 1


def test_wizard_level_none_when_absent():
    html = (_RAW / "unit" / "blood-knights.html").read_text(encoding="utf-8")
    url = "https://tow.whfb.app/unit/blood-knights"
    result = _parser.parse(html, url, _FETCHED_AT)
    assert _unit_node(result)["wizard_level"] is None
