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
        max_neighbors_per_seed: int = 40,
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

    def list_army_units(self, army: str, category: str | None = None) -> dict[str, Any]:
        """Return the complete unit roster of an army, straight from the graph.

        Deterministic Cypher over ``BELONGS_TO`` — no vector search. Army-list
        enumeration must be complete, which semantic top-k retrieval cannot
        guarantee. The payload has the same shape as ``query()`` (``context``,
        ``sources``, ``links``, ``expansion``) so the tool layer formats both
        uniformly.

        Args:
            army: Army id slug (e.g. ``"vampire-counts"``) or exact name.
            category: Optional case-insensitive filter matched against the
                unit category, army category, or troop type names.
        """
        driver = getattr(self.traversal, "driver", None)
        if driver is None:
            return self._empty_roster(army)

        # Accept both the id slug and the display name; also slugify the input
        # so "Vampire Counts" finds army id "vampire-counts".
        slugified = army.strip().lower().replace(" ", "-")
        cypher = """
            MATCH (u:Unit)-[:BELONGS_TO]->(a:Army)
            WHERE a.id = $army OR a.id = $slug OR toLower(a.name) = toLower($army)
            OPTIONAL MATCH (u)-[:HAS_TYPE]->(tt:TroopType)
            RETURN a.name AS army_name,
                   u.id AS id,
                   u.name AS name,
                   u.url AS url,
                   u.unit_category AS unit_category,
                   u.army_category AS army_category,
                   u.cost_points_per_model AS cost,
                   u.unit_size_min AS size_min,
                   u.unit_size_max AS size_max,
                   collect(DISTINCT tt.name) AS troop_types
            ORDER BY u.unit_category, u.name
        """
        with driver.session() as session:
            result = session.run(cypher, army=army.strip(), slug=slugified)
            rows = [dict(record) for record in result]

        if category:
            needle = category.strip().lower()
            rows = [
                row
                for row in rows
                if any(
                    value and needle in value.lower()
                    for value in (
                        row.get("unit_category"),
                        row.get("army_category"),
                        *(row.get("troop_types") or []),
                    )
                )
            ]

        if not rows:
            return self._empty_roster(army, category)

        army_name = rows[0].get("army_name") or army
        sources: list[dict[str, Any]] = []
        lines: list[str] = []
        for row in rows:
            details = self._roster_details(row)
            text = f"{row['name']} ({army_name}): {details}" if details else f"{row['name']}"
            sources.append(
                {
                    "id": row["id"],
                    "label": "Unit",
                    "name": row["name"],
                    "text": text,
                    "url": row.get("url"),
                }
            )
            lines.append(f"- [{row['id']}] {row['name']}: {details}")

        filter_str = f", category filter: {category!r}" if category else ""
        context = "\n".join(
            [
                f"## Units of {army_name} ({len(sources)} entries{filter_str})",
                "(Complete roster from the knowledge graph. Core/Special/Rare army-list "
                "slots are not recorded per unit; query the army's composition rules "
                "for slot limits.)",
                *lines,
            ]
        )
        return {"context": context, "sources": sources, "links": [], "expansion": []}

    @staticmethod
    def _empty_roster(army: str, category: str | None = None) -> dict[str, Any]:
        """Payload for an army/category combination with no matching units."""
        detail = f" with category {category!r}" if category else ""
        return {
            "context": (
                f"No units found for army {army!r}{detail}. Use the army's id slug "
                '(e.g. "vampire-counts") or its exact English name.'
            ),
            "sources": [],
            "links": [],
            "expansion": [],
        }

    @staticmethod
    def _roster_details(row: dict[str, Any]) -> str:
        """One-line summary of a roster row (category, points, size)."""
        details: list[str] = []
        if row.get("unit_category"):
            details.append(row["unit_category"])
        if row.get("army_category") and row["army_category"] != row.get("unit_category"):
            details.append(row["army_category"])
        troop_types = [t for t in (row.get("troop_types") or []) if t]
        if troop_types:
            details.append(", ".join(troop_types))
        if row.get("cost") is not None:
            details.append(f"{row['cost']} pts/model")
        if row.get("size_min") is not None:
            size_max = row.get("size_max")
            size = f"{row['size_min']}-{size_max}" if size_max else f"{row['size_min']}+"
            details.append(f"unit size {size}")
        return "; ".join(details)

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
            text = seed.get("text") or seed.get("name") or ""
            extra = self._seed_summary(seed.get("label"), seed_props.get(seed["id"], {}))
            if extra:
                text = f"{text} {extra}".strip()
            parts.append(
                f"- [{seed['id']}] {seed.get('name', 'Unnamed')} "
                f"({seed.get('label', 'Node')}): {text}"
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
        if label == "Upgrade":
            return RAGPipeline._upgrade_cost_summary(props)
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
        if label == "Upgrade":
            return RAGPipeline._upgrade_cost_summary(props)
        return ""

    @staticmethod
    def _upgrade_cost_summary(props: dict[str, Any]) -> str:
        """Render an Upgrade node's points cost (e.g. mount/equipment options).

        ``Upgrade`` nodes carry the cost that answers "how much for X" questions
        (mount options, wargear swaps, command group additions) but have no
        prose ``text`` field of their own, so without this the cost is silently
        dropped from what the agent sees during graph expansion.
        """
        if props.get("points_cost") is None:
            return ""
        unit_suffix = {"per_model": "pt/model", "per_unit": "pts/unit"}.get(
            props.get("cost_unit"), "pts"
        )
        return f"(+{props['points_cost']} {unit_suffix})"
