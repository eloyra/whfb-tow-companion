"""Tests for the GraphRAG tool factory."""

from __future__ import annotations

import json
from typing import Any

from backend.rag.tools import build_tools, use_native_citations


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
                },
                {
                    "id": "fear",
                    "label": "SpecialRule",
                    "name": "Fear",
                    "text": "Causes Fear in enemies.",
                    "url": "https://tow.whfb.app/special-rules/fear",
                    "score": 0.90,
                },
            ],
            "links": [
                {
                    "source": "stubborn",
                    "target": "fear",
                    "rel_type": "REFERENCES",
                    "props": {"budget": 50, "internal_id": "x"},
                }
            ],
            "expansion": [
                {
                    "seed_id": "stubborn",
                    "rel_type": "REFERENCES",
                    "id": "terror",
                    "label": "SpecialRule",
                    "name": "Terror",
                    "text": "Causes Terror.",
                    "url": "https://tow.whfb.app/special-rules/terror",
                }
            ],
        }

    def list_army_units(self, army: str, category: str | None = None) -> dict[str, Any]:
        self.roster_call = (army, category)
        return {
            "context": f"## Units of {army} (1 entries)",
            "sources": [
                {
                    "id": "skeleton-warriors",
                    "label": "Unit",
                    "name": "Skeleton Warriors",
                    "text": "Skeleton Warriors (Vampire Counts): Infantry; 6 pts/model",
                    "url": "https://tow.whfb.app/unit/skeleton-warriors",
                }
            ],
            "links": [],
            "expansion": [],
        }


def _tools_by_name(pipeline: Any, native: bool) -> dict[str, Any]:
    return {t.name: t for t in build_tools(pipeline, native_citations=native)}


def test_build_tools_exposes_archive_and_roster_tools() -> None:
    tools = _tools_by_name(FakeRAGPipeline(), native=False)
    assert set(tools) == {"query_warhammer_archive", "list_army_units"}


def test_use_native_citations_override_and_env(monkeypatch) -> None:
    assert use_native_citations(True) is True
    assert use_native_citations(False) is False
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert use_native_citations() is True
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    assert use_native_citations() is False


def test_tool_returns_trimmed_payload_with_normalized_sources() -> None:
    """The LLM-visible tool payload should be context + sources, and url -> source_url."""
    tool = _tools_by_name(FakeRAGPipeline(), native=False)["query_warhammer_archive"]
    result = json.loads(tool.invoke({"query": "stubborn"}))

    assert set(result.keys()) == {"context", "sources"}
    assert result["context"] == "Context for: stubborn"
    assert len(result["sources"]) == 2

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
    """Anthropic-native mode returns only citable search_result content blocks.

    Anthropic rejects a tool_result whose content mixes a plain ``text`` block
    with ``search_result`` blocks, so no metadata block may appear alongside
    them; the content list must be homogeneous.
    """
    tool = _tools_by_name(FakeRAGPipeline(), native=True)["query_warhammer_archive"]
    msg = tool.invoke(
        {
            "name": "query_warhammer_archive",
            "args": {"query": "stubborn"},
            "id": "call_1",
            "type": "tool_call",
        }
    )

    assert isinstance(msg.content, list)
    assert all(block["type"] == "search_result" for block in msg.content)
    assert len(msg.content) == 3  # 2 seeds + 1 expansion neighbour
    assert msg.content[0]["title"] == "Stubborn"
    assert msg.content[0]["source"] == "https://tow.whfb.app/special-rules/stubborn"
    assert msg.content[0]["citations"]["enabled"] is True

    # Context + source metadata travel out-of-band via .artifact, never inline.
    assert msg.artifact["sources"][0]["id"] == "stubborn"
    assert msg.artifact["context"] == "Context for: stubborn"


def test_native_blocks_carry_graph_relationships() -> None:
    """Seed blocks must include their direct edges: the model never sees the
    ``context`` string on the Anthropic path, so the graph structure has to
    ride inside the block text or GraphRAG degrades to plain vector RAG."""
    tool = _tools_by_name(FakeRAGPipeline(), native=True)["query_warhammer_archive"]
    msg = tool.invoke(
        {
            "name": "query_warhammer_archive",
            "args": {"query": "stubborn fear"},
            "id": "call_1",
            "type": "tool_call",
        }
    )

    stubborn_text = msg.content[0]["content"][0]["text"]
    fear_text = msg.content[1]["content"][0]["text"]
    for text in (stubborn_text, fear_text):
        assert "Graph relationships:" in text
        assert "[stubborn] --REFERENCES--" in text
        assert "[fear]" in text

    # Readable link props are kept, internal ones dropped.
    assert '"budget": 50' in stubborn_text
    assert "internal_id" not in stubborn_text


def test_native_expansion_blocks_are_labelled_as_related_context() -> None:
    tool = _tools_by_name(FakeRAGPipeline(), native=True)["query_warhammer_archive"]
    msg = tool.invoke(
        {
            "name": "query_warhammer_archive",
            "args": {"query": "stubborn"},
            "id": "call_1",
            "type": "tool_call",
        }
    )

    terror_text = msg.content[2]["content"][0]["text"]
    assert terror_text.startswith("Related context for [stubborn] (via REFERENCES).")
    assert "Causes Terror." in terror_text


class UpgradePipeline:
    """Fake pipeline whose sole expansion neighbour is an Upgrade node.

    ``Upgrade`` nodes (mount options, wargear swaps) have no prose ``text``
    field -- their points cost is a bare property. Regression test for the
    bug where that cost silently never reached the agent on either citation
    path (native search_result blocks or the legacy JSON context string).
    """

    def query(self, query: str) -> dict[str, Any]:
        return {
            "context": "Context",
            "sources": [
                {
                    "id": "vampire-count",
                    "label": "Unit",
                    "name": "Vampire Count",
                    "text": "Vampire Count profile text.",
                    "url": "https://tow.whfb.app/unit/vampire-count",
                }
            ],
            "links": [],
            "expansion": [
                {
                    "seed_id": "vampire-count",
                    "rel_type": "HAS_UPGRADE",
                    "id": "vampire-count#upgrade-6",
                    "label": "Upgrade",
                    "name": "Nightmare",
                    "text": "",
                    "url": None,
                    "points_cost": 16,
                    "cost_unit": "flat",
                }
            ],
        }


def test_native_expansion_surfaces_upgrade_cost() -> None:
    tool = _tools_by_name(UpgradePipeline(), native=True)["query_warhammer_archive"]
    msg = tool.invoke(
        {
            "name": "query_warhammer_archive",
            "args": {"query": "nightmare mount cost"},
            "id": "call_1",
            "type": "tool_call",
        }
    )

    upgrade_text = msg.content[1]["content"][0]["text"]
    assert "+16 pts" in upgrade_text


def test_native_sources_metadata_stays_aligned_with_blocks() -> None:
    """``search_result_index`` citations are positional: the artifact sources
    list must match the content blocks one-to-one, including when a node has
    no text and is skipped."""

    class PipelineWithTextlessNode(FakeRAGPipeline):
        def query(self, query: str) -> dict[str, Any]:
            result = super().query(query)
            # A node with neither text nor name produces no block and must be
            # dropped from the metadata too, or all later indices shift.
            result["sources"].insert(1, {"id": "ghost", "label": "Unit", "text": ""})
            return result

    tool = _tools_by_name(PipelineWithTextlessNode(), native=True)["query_warhammer_archive"]
    msg = tool.invoke(
        {
            "name": "query_warhammer_archive",
            "args": {"query": "stubborn"},
            "id": "call_1",
            "type": "tool_call",
        }
    )

    assert len(msg.content) == len(msg.artifact["sources"])
    block_titles = [block["title"] for block in msg.content]
    meta_names = [src["name"] for src in msg.artifact["sources"]]
    assert block_titles == meta_names
    assert "ghost" not in {src["id"] for src in msg.artifact["sources"]}


def test_native_sources_metadata_includes_clean_text_for_frontend_preview() -> None:
    """The frontend's citation hover preview reads ``text`` off the native
    artifact's ``sources`` metadata (see SourcesList.tsx). It must be the
    node's own prose — not the graph-relationship-annotated version mixed
    into the model-facing search_result block, which would show a human
    "Graph relationships:\n- [x] --REFERENCES--> [y]" formatting artifact."""
    tool = _tools_by_name(FakeRAGPipeline(), native=True)["query_warhammer_archive"]
    msg = tool.invoke(
        {
            "name": "query_warhammer_archive",
            "args": {"query": "stubborn"},
            "id": "call_1",
            "type": "tool_call",
        }
    )

    meta_by_id = {src["id"]: src for src in msg.artifact["sources"]}
    assert meta_by_id["stubborn"]["text"] == "Stubborn units ignore Combat Result modifiers."

    # The model-facing block for the same node DOES carry the annotation —
    # confirming the split, not just that the metadata field happens to exist.
    block_by_title = {block["title"]: block for block in msg.content}
    block_text = block_by_title["Stubborn"]["content"][0]["text"]
    assert "Graph relationships:" in block_text


def test_roster_tool_returns_legacy_payload() -> None:
    pipeline = FakeRAGPipeline()
    tool = _tools_by_name(pipeline, native=False)["list_army_units"]
    result = json.loads(tool.invoke({"army": "vampire-counts", "category": "Infantry"}))

    assert pipeline.roster_call == ("vampire-counts", "Infantry")
    assert result["sources"][0]["id"] == "skeleton-warriors"
    assert result["sources"][0]["source_url"] == "https://tow.whfb.app/unit/skeleton-warriors"


def test_roster_tool_returns_native_blocks() -> None:
    tool = _tools_by_name(FakeRAGPipeline(), native=True)["list_army_units"]
    msg = tool.invoke(
        {
            "name": "list_army_units",
            "args": {"army": "vampire-counts"},
            "id": "call_1",
            "type": "tool_call",
        }
    )

    assert isinstance(msg.content, list)
    assert all(block["type"] == "search_result" for block in msg.content)
    assert msg.content[0]["title"] == "Skeleton Warriors"
    assert msg.artifact["sources"][0]["id"] == "skeleton-warriors"
