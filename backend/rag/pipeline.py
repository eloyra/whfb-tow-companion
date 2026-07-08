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
                    "No relevant information was found in the Warhammer: The Old World archive."
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

        seed_ids = [s["id"] for s in seeds]
        expansion_ids = list({e["id"] for e in expansion})
        seed_props = self._node_properties(seed_ids)
        neighbor_props = self._node_properties(expansion_ids)

        parts.append("## Retrieved sources")
        for seed in seeds:
            score = seed.get("score")
            score_str = f" (score: {score:.3f})" if score is not None else ""
            text = seed.get("text") or seed.get("name") or ""
            extra = self._seed_summary(seed.get("label"), seed_props.get(seed["id"], {}))
            if extra:
                text = f"{text} {extra}".strip()
            parts.append(
                f"- [{seed['id']}] {seed.get('name', 'Unnamed')} "
                f"({seed.get('label', 'Node')}){score_str}: {text}"
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
                extra = self._neighbor_summary(row.get("label"), neighbor_props.get(row["id"], {}))
                text = row.get("text") or row.get("name") or ""
                if extra:
                    text = f"{text} {extra}".strip()
                parts.append(
                    f"- [{row['seed_id']}] --{row['rel_type']}→ "
                    f"[{row['id']}] {row.get('name', '')}: {text}"
                )

        return "\n".join(parts)

    def _node_properties(self, node_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch node properties (excluding embeddings) for a list of ids."""
        if not node_ids or not hasattr(self.traversal, "driver"):
            return {}
        cypher = """
            UNWIND $ids AS nid
            MATCH (n {id: nid})
            RETURN nid, apoc.map.removeKeys(properties(n), ['embedding']) AS props
        """
        with self.traversal.driver.session() as session:
            result = session.run(cypher, ids=node_ids)
            return {rec["nid"]: dict(rec["props"]) for rec in result}

    @staticmethod
    def _seed_summary(label: str | None, props: dict[str, Any]) -> str:
        """Extra human-readable details for seed nodes."""
        if label == "Unit":
            details: list[str] = []
            if props.get("cost_points_per_model") is not None:
                details.append(f"{props['cost_points_per_model']} pts/model")
            if props.get("unit_size_min") is not None:
                size_max = props.get("unit_size_max")
                if size_max:
                    size = f"{props['unit_size_min']}-{size_max}"
                else:
                    size = f"{props['unit_size_min']}+"
                details.append(f"Unit size {size}")
            if props.get("base_width_mm") and props.get("base_depth_mm"):
                details.append(f"Base {props['base_width_mm']}x{props['base_depth_mm']}mm")
            if props.get("army_category"):
                details.append(f"Category {props['army_category']}")
            return f"({' ; '.join(details)})" if details else ""
        if label == "MagicItem":
            details = []
            if props.get("item_type"):
                details.append(props["item_type"].replace("_", " "))
            if props.get("points_cost") is not None:
                details.append(f"{props['points_cost']} pts")
            return f"({' ; '.join(details)})" if details else ""
        return ""

    @staticmethod
    def _neighbor_summary(label: str | None, props: dict[str, Any]) -> str:
        """Extra details for expanded neighbor nodes."""
        if label == "Profile":
            stats = []
            for stat in ("M", "WS", "BS", "S", "T", "W", "I", "A", "Ld"):
                val = props.get(stat)
                if val is not None:
                    stats.append(f"{stat}{val}")
            return f"Stats: {' '.join(stats)}" if stats else ""
        if label == "Unit":
            details = []
            if props.get("cost_points_per_model") is not None:
                details.append(f"{props['cost_points_per_model']} pts/model")
            if props.get("base_width_mm") and props.get("base_depth_mm"):
                details.append(f"Base {props['base_width_mm']}x{props['base_depth_mm']}mm")
            return f"({' ; '.join(details)})" if details else ""
        return ""
