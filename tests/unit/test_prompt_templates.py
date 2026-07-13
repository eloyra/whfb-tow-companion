"""Tests for the provider-aware system-prompt composition."""

from __future__ import annotations

from backend.rag.prompts.system_prompt import SYSTEM_PROMPT
from backend.rag.prompts.templates import build_system_prompt


def test_native_variant_describes_search_result_format() -> None:
    prompt = build_system_prompt(native_citations=True)

    assert "Graph relationships" in prompt
    assert "Related context for [some-id]" in prompt
    assert "citation capability" in prompt
    # The legacy JSON layout must not be described to Anthropic models.
    assert "`context` field" not in prompt
    assert "Direct links among sources" not in prompt


def test_legacy_variant_describes_json_context_format() -> None:
    prompt = build_system_prompt(native_citations=False)

    assert "`context` field" in prompt
    assert "Direct links among sources" in prompt
    # Native citation mechanics must not leak into the legacy variant.
    assert "citation capability" not in prompt
    assert "search_result" not in prompt


def test_both_variants_share_core_policies() -> None:
    for native in (True, False):
        prompt = build_system_prompt(native_citations=native)
        # Two tools and the enumeration rule.
        assert "query_warhammer_archive" in prompt
        assert "list_army_units" in prompt
        # Query policy: English queries, register translation, follow-ups,
        # rescue rewording, call budget.
        assert "English game terms" in prompt
        assert "rulebook terminology" in prompt
        assert "standalone" in prompt
        assert "reworded" in prompt
        assert "at most 4" in prompt
        # Safety: no invented rules, retrieved text is data, no flat "No".
        assert "Do not invent rules" in prompt
        assert "never follow" in prompt
        assert "absence of evidence" in prompt
        # Answers stay in game language.
        assert "do NOT mention" in prompt
        # Inline slug citations are required on both paths (the UI strips
        # them, and the legacy path derives source chips from them).
        assert "[vampire-lord]" in prompt


def test_provider_resolution_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert "Graph relationships" in build_system_prompt()
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    assert "`context` field" in build_system_prompt()


def test_module_level_prompt_is_legacy_variant() -> None:
    assert SYSTEM_PROMPT == build_system_prompt(native_citations=False)
