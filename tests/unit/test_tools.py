"""Tests for the GraphRAG tool factory."""

from __future__ import annotations

import json
from typing import Any

from backend.rag.tools import build_tools


class FakeRAGPipeline:
    """Fake pipeline returning the full internal payload shape."""

    def query(self, query: str) -> dict[str, Any]:
        return {
            "context": f"Context for: {query}",
            "sources": [
                {
                    "id": "stubborn",
                    "label": "SpecialRule",
                    "name": "Stubborn",
                    "text": "Stubborn units ignore Combat Result modifiers.",
                    "url": "https://tow.whfb.app/special-rules/stubborn",
                    "score": 0.95,
                }
            ],
            "links": [
                {
                    "source": "stubborn",
                    "target": "fear",
                    "rel_type": "REFERENCES",
                }
            ],
            "expansion": [
                {
                    "seed_id": "stubborn",
                    "rel_type": "REFERENCES",
                    "id": "terror",
                }
            ],
        }


def test_tool_returns_trimmed_payload_with_normalized_sources() -> None:
    """The LLM-visible tool payload should be context + sources, and url -> source_url."""
    tool = build_tools(FakeRAGPipeline(), native_citations=False)[0]
    result = json.loads(tool.invoke({"query": "stubborn"}))

    assert set(result.keys()) == {"context", "sources"}
    assert result["context"] == "Context for: stubborn"
    assert len(result["sources"]) == 1

    source = result["sources"][0]
    assert source["id"] == "stubborn"
    assert source["label"] == "SpecialRule"
    assert source["name"] == "Stubborn"
    assert source["source_url"] == "https://tow.whfb.app/special-rules/stubborn"
    assert "url" not in source
    assert "score" not in source
    assert "links" not in result
    assert "expansion" not in result


def test_tool_returns_native_search_result_blocks() -> None:
    """Anthropic-native mode returns citable search_result content blocks."""
    tool = build_tools(FakeRAGPipeline(), native_citations=True)[0]
    result = tool.invoke({"query": "stubborn"})

    assert isinstance(result, list)
    assert result[0]["type"] == "text"
    meta = json.loads(result[0]["text"])
    assert meta["sources"][0]["id"] == "stubborn"

    search_blocks = [b for b in result if b.get("type") == "search_result"]
    assert len(search_blocks) >= 1
    assert search_blocks[0]["title"] == "Stubborn"
    assert search_blocks[0]["source"] == "https://tow.whfb.app/special-rules/stubborn"
    assert search_blocks[0]["citations"]["enabled"] is True
