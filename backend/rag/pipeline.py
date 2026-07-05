"""RAG pipeline orchestration.

``RAGPipeline`` combines semantic retrieval (seed nodes) with graph traversal
(neighborhood context + direct seed-to-seed links) and formats the result into a
single context payload for the LLM.
"""

from __future__ import annotations

import json
from typing import Any


class RAGPipeline:
    """End-to-end GraphRAG pipeline: retrieve → traverse → format."""

    def __init__(
        self,
        retriever: Any,
        traversal: Any,
        *,
        top_k: int = 8,
        max_neighbors_per_seed: int = 6,
    ) -> None:
        self.retriever = retriever
        self.traversal = traversal
        self.top_k = top_k
        self.max_neighbors_per_seed = max_neighbors_per_seed

    def query(self, user_query: str) -> dict[str, Any]:
        """Run the full GraphRAG pipeline for ``user_query``.

        Returns a dict with:
        - ``context``: a human-readable string for the LLM containing sources,
          direct links among them, and 1-hop neighborhood context.
        - ``sources``: the seed nodes retrieved by semantic search.
        - ``links``: direct edges among the seed nodes.
        - ``expansion``: bounded 1-hop neighbors of the seed nodes.
        """
        seeds = self.retriever.retrieve(user_query)
        if not seeds:
            return {
                "context": (
                    "No relevant information was found in the "
                    "Warhammer: The Old World archive."
                ),
                "sources": [],
                "links": [],
                "expansion": [],
            }

        seed_ids = [s["id"] for s in seeds]
        expansion = self.traversal.expand(
            seed_ids,
            max_neighbors_per_seed=self.max_neighbors_per_seed,
        )
        links = self.traversal.links_between(seed_ids)

        context = self._format_context(seeds, links, expansion)
        return {
            "context": context,
            "sources": seeds,
            "links": links,
            "expansion": expansion,
        }

    def _format_context(
        self,
        seeds: list[dict[str, Any]],
        links: list[dict[str, Any]],
        expansion: list[dict[str, Any]],
    ) -> str:
        """Build a concise, citation-ready context string for the LLM."""
        parts: list[str] = []

        parts.append("## Retrieved sources")
        for seed in seeds:
            score = seed.get("score")
            score_str = f" (score: {score:.3f})" if score is not None else ""
            parts.append(
                f"- [{seed['id']}] {seed.get('name', 'Unnamed')} "
                f"({seed.get('label', 'Node')}){score_str}: {seed.get('text', '')}"
            )

        if links:
            parts.append("\n## Direct links among sources")
            parts.append(f"({len(links)} direct edge(s) among the retrieved sources)")
            for link in links:
                props = link.get("props") or {}
                props_str = ""
                if props:
                    # Filter to a few readable properties; avoid dumping huge dicts.
                    keep = {"budget", "alliance_type", "via_upgrade"}
                    readable = {k: v for k, v in props.items() if k in keep}
                    if readable:
                        props_str = " " + json.dumps(readable, ensure_ascii=False)
                parts.append(
                    f"- [{link['source']}] --{link['rel_type']}--{props_str}→ [{link['target']}]"
                )
        else:
            parts.append("\n## Direct links among sources")
            parts.append("(No direct edge was found among the retrieved sources.)")

        if expansion:
            parts.append("\n## Related context")
            for row in expansion:
                parts.append(
                    f"- [{row['seed_id']}] --{row['rel_type']}→ "
                    f"[{row['id']}] {row.get('name', '')}: {row.get('text', '')}"
                )

        return "\n".join(parts)
