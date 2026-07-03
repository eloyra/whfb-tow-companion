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
        graph hop, and returns matching nodes with citations.

        Returns a JSON object with keys:
        - ``context``: a formatted summary of retrieved sources, direct links
          among them, and related 1-hop context.
        - ``sources``: the seed nodes retrieved by semantic search. Cite any
          source you use with ``[source-id]``.
        - ``links``: direct edges among the retrieved sources (useful for
          eligibility/capability questions like "can X use Y?" or "can X ride Y?").
        - ``expansion``: related nodes one hop away from the seeds.

        Args:
            query: A clear, specific question or search phrase. Rephrase the
                user's question if needed to improve retrieval.
        """
        result = pipeline.query(query)
        return json.dumps(result, ensure_ascii=False)

    return [query_warhammer_archive]
