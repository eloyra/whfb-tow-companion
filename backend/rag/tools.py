"""Tools exposed to the chat agent.

The tools are built at runtime by ``build_tools(pipeline)`` so they close over
the injected ``RAGPipeline``:

- ``query_warhammer_archive`` — semantic search + 1-hop graph traversal.
- ``list_army_units`` — deterministic army roster (Cypher, no vector search).

Both tools return their result through the same pair of builders so provider
handling stays uniform: Anthropic gets citable ``search_result`` content
blocks, everything else gets a JSON string.
"""

from __future__ import annotations

import json
import os
from typing import Any

from langchain.tools import tool

# Maximum number of citable search_result blocks returned to Anthropic models
# for a semantic-search result. More blocks give finer citations but increase
# input-token cost. Seeds are listed first and always included ahead of this
# cap (see _citable_nodes); this budget mainly governs how much of each
# seed's 1-hop expansion survives. Sized to comfortably fit a full seed's
# expansion under graph_traversal.expand()'s current per-seed ceiling (40,
# itself split across per-relation-type caps) — a lower value here would
# silently re-drop content that traversal was deliberately raised to keep
# (e.g. a Unit's full mount/upgrade list), defeating that fix.
_MAX_CITABLE_NODES = 60

# Higher cap for the army-roster tool: a roster is only useful when complete,
# and its per-unit blocks are one line each, so the token cost stays small.
_MAX_ROSTER_NODES = 100

# Relationship properties worth surfacing to the model; everything else is
# internal bookkeeping and would only add noise.
_READABLE_LINK_PROPS = {"budget", "alliance_type", "via_upgrade"}


def use_native_citations(override: bool | None = None) -> bool:
    """Resolve whether Anthropic-native ``search_result`` blocks are in use.

    ``build_tools`` and ``build_system_prompt`` share this switch so the
    system prompt always describes the tool-result format the model actually
    receives.
    """
    if override is not None:
        return override
    return os.getenv("LLM_PROVIDER", "ollama").lower() == "anthropic"


def _source_url(node: dict[str, Any]) -> str:
    """Return the canonical source URL for a retrieved node."""
    return node.get("source_url") or node.get("url") or ""


def _node_text(node: dict[str, Any]) -> str:
    """Return non-empty text for a node, falling back to its name.

    ``Upgrade`` nodes (mount options, wargear swaps, command additions) carry
    their points cost as a bare property with no prose ``text`` field, so it
    is appended here — otherwise "how much for X" questions silently lose the
    number on every citation path (native search_result blocks and the legacy
    JSON path both flow through this helper).
    """
    text = (node.get("text") or node.get("name") or "").strip()
    if node.get("label") == "Upgrade" and node.get("points_cost") is not None:
        unit_suffix = {"per_model": "pt/model", "per_unit": "pts/unit"}.get(
            node.get("cost_unit"), "pts"
        )
        text = f"{text} (+{node['points_cost']} {unit_suffix})".strip()
    return text


def _citable_nodes(result: dict[str, Any], max_nodes: int) -> list[dict[str, Any]]:
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

    return nodes[:max_nodes]


def _format_link(link: dict[str, Any]) -> str:
    """Render one seed-to-seed graph edge as a readable line."""
    props = link.get("props") or {}
    readable = {k: v for k, v in props.items() if k in _READABLE_LINK_PROPS}
    props_str = f" {json.dumps(readable, ensure_ascii=False)}" if readable else ""
    return f"[{link['source']}] --{link['rel_type']}--{props_str}> [{link['target']}]"


def _relationship_annotations(
    result: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Per-node graph annotations for the native ``search_result`` path.

    On Anthropic, the pipeline's ``context`` string (which carries the graph
    structure on the legacy path) never reaches the model — only the content
    blocks do. Without these annotations the model would see bare node texts
    with no edges at all, defeating the graph half of GraphRAG.

    Returns two maps keyed by node id:
    - ``related_by_node``: header lines for expansion nodes explaining which
      seed they hang off and via which relationship.
    - ``links_by_node``: "Graph relationships" lines for seed nodes listing
      their direct edges to other retrieved seeds.
    """
    related_by_node: dict[str, list[str]] = {}
    for row in result.get("expansion", []):
        if not isinstance(row, dict) or not row.get("id"):
            continue
        related_by_node.setdefault(row["id"], []).append(
            f"Related context for [{row.get('seed_id')}] (via {row.get('rel_type')})."
        )

    links_by_node: dict[str, list[str]] = {}
    for link in result.get("links", []):
        if not isinstance(link, dict):
            continue
        line = f"- {_format_link(link)}"
        for endpoint in (link.get("source"), link.get("target")):
            if endpoint:
                links_by_node.setdefault(endpoint, []).append(line)

    return related_by_node, links_by_node


def _build_native_tool_result(
    result: dict[str, Any],
    *,
    max_nodes: int = _MAX_CITABLE_NODES,
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

    Because the model never sees the ``context`` string here, the graph
    structure (seed-to-seed edges, expansion relationships) is folded into
    each block's text via ``_relationship_annotations``.

    The ``sources`` artifact list is built in the same loop as the content
    blocks so both stay index-aligned: ``VercelStream`` resolves each native
    citation's ``search_result_index`` positionally against that list.
    """
    citable = _citable_nodes(result, max_nodes)
    related_by_node, links_by_node = _relationship_annotations(result)

    content_blocks: list[dict[str, Any]] = []
    sources_meta: list[dict[str, Any]] = []
    for node in citable:
        text = _node_text(node)
        if not text:
            continue
        nid = node.get("id")
        # Captured before the graph-relationship annotations below are mixed
        # in — those are LLM-context formatting (raw "[id] --REL--> [id2]"
        # lines), not something a human should see in a citation preview.
        display_text = text

        related_lines = related_by_node.get(nid, [])
        if related_lines:
            text = "\n".join(related_lines) + "\n\n" + text

        link_lines = links_by_node.get(nid, [])
        if link_lines:
            text = text + "\n\nGraph relationships:\n" + "\n".join(link_lines)

        sources_meta.append(
            {
                "id": nid,
                "name": node.get("name"),
                "label": node.get("label"),
                "text": display_text,
                "source_url": _source_url(node),
                "book": node.get("book"),
                "page": node.get("page"),
            }
        )
        content_blocks.append(
            {
                "type": "search_result",
                "title": node.get("name") or nid,
                "source": _source_url(node) or nid,
                "citations": {"enabled": True},
                "content": [{"type": "text", "text": text}],
            }
        )

    artifact = {"context": result.get("context", ""), "sources": sources_meta}

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
            "book": src.get("book"),
            "page": src.get("page"),
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
        pipeline: The ``RAGPipeline`` instance the tools should query.
        native_citations: When ``True``, return Anthropic-native
            ``search_result`` content blocks. When ``False`` (default for tests
            and non-Anthropic providers), return a JSON string. When ``None``,
            derive from the ``LLM_PROVIDER`` environment variable.
    """
    native = use_native_citations(native_citations)

    @tool(response_format="content_and_artifact")
    def query_warhammer_archive(
        query: str,
    ) -> tuple[list[dict[str, Any]] | str, dict[str, Any]]:
        """Query the Warhammer: The Old World knowledge graph.

        Use this tool for **any factual question** about rules, units, special
        rules, magic items, spells, lore, terrain, or FAQ/errata rulings. It
        performs semantic search over the graph, expands the results by one
        graph hop, and returns citable source entries including the direct
        graph relationships found among them.

        Do NOT use it to enumerate an army's units — use ``list_army_units``
        for that; semantic search returns only the closest matches, never a
        complete roster.

        How to phrase ``query`` — always in English, using official English
        game terms, with casual table-talk translated into rulebook wording:
        - Rule lookup: "Stubborn special rule"
        - Rule interaction: combine both concept names, e.g.
          "Regeneration Flaming Attacks interaction"
        - Eligibility ("can X use/ride Y?"): include BOTH the subject and the
          object, e.g. "Vampire Lord Nightshroud" or "Orc Warboss Wyvern".
          This maximises the chance that both entries are retrieved and the
          direct relationship between them is found.
        - Unit stats: "Blood Knights profile"
        - Lore/spell: "Lore of Battle Magic" or "Oaken Shield spell"
        - Follow-up questions: rewrite them standalone, resolving pronouns to
          the entity names from the conversation.

        You may call this tool more than once when a question needs multiple
        concepts; reword the query (official rule name, synonyms, the general
        mechanic) if the first result misses the concept.

        Args:
            query: A clear, specific search phrase in English. Rephrase the
                user's question if needed to improve retrieval.
        """
        result = pipeline.query(query)
        if native:
            return _build_native_tool_result(result)
        return _build_legacy_tool_result(result)

    @tool(response_format="content_and_artifact")
    def list_army_units(
        army: str,
        category: str | None = None,
    ) -> tuple[list[dict[str, Any]] | str, dict[str, Any]]:
        """List every unit of an army with points cost and unit size.

        Use this tool — never semantic search — whenever you need to
        enumerate an army's units (army-list building, "what units can X
        field?"). It reads the roster directly from the knowledge graph, so
        the result is complete and deterministic.

        The roster does NOT record Core/Special/Rare army-list slots; if slot
        limits matter, query the army's composition rules with
        ``query_warhammer_archive``.

        Args:
            army: Army id slug or exact English name, e.g. "vampire-counts"
                or "Vampire Counts".
            category: Optional case-insensitive filter matched against the
                unit's category ("Characters", "Named Characters", "Mounts",
                "Infantry", "Cavalry", ...) or troop type. Omit it to get the
                full roster.
        """
        result = pipeline.list_army_units(army, category)
        if native:
            return _build_native_tool_result(result, max_nodes=_MAX_ROSTER_NODES)
        return _build_legacy_tool_result(result)

    return [query_warhammer_archive, list_army_units]
