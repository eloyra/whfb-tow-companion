"""Tools exposed to the chat agent.

The single tool ``query_warhammer_archive`` is built at runtime by
``build_tools(pipeline)`` so it closes over the injected ``RAGPipeline``.
"""

from __future__ import annotations

import json
import os
from typing import Any

from langchain.tools import tool

# Maximum number of citable search_result blocks returned to Anthropic models.
# More blocks give finer citations but increase input-token cost.
_MAX_CITABLE_NODES = 20


def _source_url(node: dict[str, Any]) -> str:
    """Return the canonical source URL for a retrieved node."""
    return node.get("source_url") or node.get("url") or ""


def _node_text(node: dict[str, Any]) -> str:
    """Return non-empty text for a node, falling back to its name."""
    return (node.get("text") or node.get("name") or "").strip()


def _citable_nodes(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Build an ordered, deduplicated list of nodes that can be cited.

    Seeds are listed first, then one-hop expansion neighbours. The order is
    preserved because Anthropic's ``search_result_index`` is positional.
    """
    seen: set[str] = set()
    nodes: list[dict[str, Any]] = []

    for node in result.get("sources", []):
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if not nid or nid in seen:
            continue
        seen.add(nid)
        nodes.append(node)

    for node in result.get("expansion", []):
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if not nid or nid in seen:
            continue
        seen.add(nid)
        nodes.append(node)

    return nodes[:_MAX_CITABLE_NODES]


def _build_native_tool_result(
    result: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build Anthropic-native tool-result content blocks + out-of-band metadata.

    Anthropic rejects a tool_result whose content mixes a plain ``text`` block
    with ``search_result`` blocks ("if any blocks ... are of type
    `search_result`, all blocks must be of that type"). So the content sent to
    the model is *only* ``search_result`` blocks (one per citable node, in
    order — this order is what ``search_result_index`` citations refer back
    to). The context summary and ``sources`` metadata instead travel as the
    LangChain tool ``artifact``, which is attached to the ``ToolMessage`` for
    local use but never serialized into the API request.
    """
    citable = _citable_nodes(result)

    sources_meta = [
        {
            "id": node.get("id"),
            "name": node.get("name"),
            "label": node.get("label"),
            "source_url": _source_url(node),
        }
        for node in citable
    ]
    artifact = {"context": result.get("context", ""), "sources": sources_meta}

    content_blocks: list[dict[str, Any]] = []
    for node in citable:
        text = _node_text(node)
        if not text:
            continue
        content_blocks.append(
            {
                "type": "search_result",
                "title": node.get("name") or node.get("id"),
                "source": _source_url(node) or node.get("id"),
                "citations": {"enabled": True},
                "content": [{"type": "text", "text": text}],
            }
        )

    if not content_blocks:
        # No citable nodes: no search_result blocks means the homogeneity rule
        # does not apply, so a plain text summary is safe here.
        content_blocks = [{"type": "text", "text": result.get("context", "")}]

    return content_blocks, artifact


def _build_legacy_tool_result(result: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return the JSON-string tool result used by non-Anthropic providers.

    Also returns the same ``sources`` list as the artifact, so downstream
    consumers (``VercelStream``, the eval harness) can read source metadata
    uniformly via ``.artifact`` regardless of provider.
    """
    visible_sources = [
        {
            "id": src.get("id"),
            "label": src.get("label"),
            "name": src.get("name"),
            "text": src.get("text"),
            "source_url": _source_url(src),
        }
        for src in result.get("sources", [])
        if isinstance(src, dict)
    ]
    visible = {
        "context": result.get("context", ""),
        "sources": visible_sources,
    }
    artifact = {"context": result.get("context", ""), "sources": visible_sources}
    return json.dumps(visible, ensure_ascii=False), artifact


def build_tools(pipeline: Any, native_citations: bool | None = None) -> list[Any]:
    """Create the agent tool list wired to the given ``RAGPipeline``.

    ``pipeline`` is typically injected via FastAPI's ``Depends(get_rag_pipeline)``.

    Args:
        pipeline: The ``RAGPipeline`` instance the tool should query.
        native_citations: When ``True``, return Anthropic-native
            ``search_result`` content blocks. When ``False`` (default for tests
            and non-Anthropic providers), return a JSON string. When ``None``,
            derive from the ``LLM_PROVIDER`` environment variable.
    """
    if native_citations is None:
        native_citations = os.getenv("LLM_PROVIDER", "ollama").lower() == "anthropic"

    use_native_citations = native_citations

    @tool(response_format="content_and_artifact")
    def query_warhammer_archive(
        query: str,
    ) -> tuple[list[dict[str, Any]] | str, dict[str, Any]]:
        """Query the Warhammer: The Old World knowledge graph.

        Use this tool for **any factual question** about rules, units, special
        rules, magic items, spells, lore, army composition, or army building.
        It performs semantic search over the graph, expands the results by one
        graph hop, and returns a readable summary plus citable source nodes.

        On Anthropic models the result is returned as citable ``search_result``
        content blocks; on other providers it returns a JSON object with keys:
        - ``context``: the primary summary to read. It contains the retrieved
          sources, any direct edges among them, and related 1-hop context.
        - ``sources``: the seed nodes retrieved by semantic search.

        How to phrase ``query``:
        - Rule lookup: "stubborn special rule"
        - Rule interaction: combine both concepts, e.g.
          "regeneration flaming attacks interaction"
        - Eligibility ("can X use/ride Y?"): include BOTH the subject and the
          object, e.g. "vampire-lord nightshroud" or "orc-warboss wyvern".
        - Unit stats: "blood-knights profile"
        - Army-list building: "vampire-counts core units points"

        You may call this tool more than once when a question needs multiple
        concepts or a list of candidates.

        Args:
            query: A clear, specific question or search phrase. Rephrase the
                user's question if needed to improve retrieval.
        """
        result = pipeline.query(query)
        if use_native_citations:
            return _build_native_tool_result(result)
        return _build_legacy_tool_result(result)

    return [query_warhammer_archive]
