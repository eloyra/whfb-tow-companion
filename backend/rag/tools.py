"""Tools exposed to the chat agent. Replace mocks with real GraphRAG calls later."""

import json

from langchain.tools import tool


@tool
def query_warhammer_archive(query: str) -> str:
    """Query the Warhammer: The Old World knowledge graph for rules, units, magic
    items, special rules, and lore. Use this tool whenever the user asks a factual
    question about the game. Returns a JSON array of matching nodes; cite the `id`
    field of any node you use.
    """
    mock_nodes = [
        {
            "id": "great-swords",
            "text": "Great Swords have the Stubborn special rule.",
        },
        {
            "id": "stubborn",
            "text": "Stubborn units ignore Combat Result modifiers when testing Break.",
        },
    ]
    return json.dumps(mock_nodes)


AGENT_TOOLS = [query_warhammer_archive]
