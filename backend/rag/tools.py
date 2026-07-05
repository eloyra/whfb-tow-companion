"""Tools exposed to the chat agent.

The single tool ``query_warhammer_archive`` is built at runtime by
``build_tools(pipeline)`` so it closes over the injected ``RAGPipeline``.
"""

from __future__ import annotations

import json
from typing import Any

from langchain.tools import tool


def build_tools(pipeline: Any) -> list[Any]:
    """Create the agent tool list wired to the given ``RAGPipeline``.

    ``pipeline`` is typically injected via FastAPI's ``Depends(get_rag_pipeline)``.
    """

    @tool
    def query_warhammer_archive(query: str) -> str:
        """Query the Warhammer: The Old World knowledge graph.

        Use this tool for **any factual question** about rules, units, special
        rules, magic items, spells, lore, army composition, or army building.
        It performs semantic search over the graph, expands the results by one
        graph hop, and returns a readable summary plus citable source nodes.

        Returns a JSON object with keys:
        - ``context``: the primary summary to read. It contains the retrieved
          sources, any direct edges among them (useful for "can X use Y?"), and
          related 1-hop context.
        - ``sources``: the seed nodes retrieved by semantic search. Cite any
          source you use with ``[source-id]``.

        How to phrase ``query``:
        - Rule lookup: "stubborn special rule"
        - Rule interaction: combine both concepts, e.g.
          "regeneration flaming attacks interaction"
        - Eligibility ("can X use/ride Y?"): include both names, e.g.
          "vampire-lord nightshroud" or "orc-warboss wyvern"
        - Unit stats: "blood-knights profile"
        - Army-list building: "vampire-counts core units points"

        You may call this tool more than once when a question needs multiple
        concepts or a list of candidates.

        Args:
            query: A clear, specific question or search phrase. Rephrase the
                user's question if needed to improve retrieval.
        """
        result = pipeline.query(query)
        visible_sources = [
            {
                "id": src.get("id"),
                "label": src.get("label"),
                "name": src.get("name"),
                "text": src.get("text"),
                "source_url": src.get("source_url") or src.get("url"),
            }
            for src in result.get("sources", [])
            if isinstance(src, dict)
        ]
        visible = {
            "context": result.get("context", ""),
            "sources": visible_sources,
        }
        return json.dumps(visible, ensure_ascii=False)

    return [query_warhammer_archive]
