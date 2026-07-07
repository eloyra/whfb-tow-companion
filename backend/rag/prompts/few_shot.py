"""Few-shot message turns for the chat agent.

These are prepended to the real conversation history so the model sees concrete
examples of:
- phrasing a good `query_warhammer_archive` call,
- reading the tool result,
- citing sources inline with `[slug]`,
- using a direct edge to answer an eligibility question,
- making multiple calls for army-list building.

The examples are intentionally compact (2 sources / 1 link) to keep token cost
under control.
"""

from __future__ import annotations

import json
from typing import Any

from langchain.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage


def _tool_result(context: str, sources: list[dict[str, Any]]) -> str:
    """Build the JSON string the tool returns for a few-shot example."""
    return json.dumps(
        {"context": context, "sources": sources},
        ensure_ascii=False,
    )


def _rule_interaction_example() -> list[AnyMessage]:
    """Example: Regeneration vs Flaming Attacks."""
    query = "regeneration flaming attacks interaction"
    sources = [
        {
            "id": "regeneration",
            "label": "SpecialRule",
            "name": "Regeneration",
            "text": "Regeneration allows a model to recover wounds...",
            "source_url": "https://tow.whfb.app/special-rules/regeneration",
        },
        {
            "id": "flaming-attacks",
            "label": "SpecialRule",
            "name": "Flaming Attacks",
            "text": "Hits from Flaming Attacks are flaming...",
            "source_url": "https://tow.whfb.app/special-rules/flaming-attacks",
        },
        {
            "id": "flammable",
            "label": "SpecialRule",
            "name": "Flammable",
            "text": (
                "A model with this special rule cannot make a Regeneration save "
                "against a wound caused by a Flaming attack."
            ),
            "source_url": "https://tow.whfb.app/special-rules/flammable",
        },
    ]
    context = (
        "## Retrieved sources\n"
        "- [regeneration] Regeneration (SpecialRule): Regeneration allows a model "
        "to regain wounds at the end of each Combat round.\n"
        "- [flaming-attacks] Flaming Attacks (SpecialRule): Hits from Flaming "
        "Attacks are flaming and cause Fear in cavalry.\n"
        "- [flammable] Flammable (SpecialRule): A model with this special rule "
        "cannot make a Regeneration save against a wound caused by a Flaming "
        "attack.\n\n"
        "## Direct links among sources\n"
        "- [flammable] --REFERENCES--> [regeneration]\n"
        "- [flammable] --REFERENCES--> [flaming-attacks]"
    )
    tool_call_id = "example_call_regen"
    return [
        HumanMessage(
            content=(
                "What happens when a unit with Regeneration is hit by "
                "Flaming Attacks?"
            )
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "query_warhammer_archive",
                    "args": {"query": query},
                    "id": tool_call_id,
                }
            ],
        ),
        ToolMessage(
            content=_tool_result(context, sources),
            tool_call_id=tool_call_id,
            name="query_warhammer_archive",
        ),
        AIMessage(
            content=(
                "Unless the unit also has the Flammable special rule, "
                "Regeneration works normally against Flaming Attacks. A model "
                "with the Flammable special rule cannot make a Regeneration save "
                "against a Flaming wound [flammable]."
            ),
        ),
    ]


def _eligibility_example() -> list[AnyMessage]:
    """Example: Can a Vampire Lord take the Nightshroud?"""
    query = "vampire-lord nightshroud"
    sources = [
        {
            "id": "vampire-lord",
            "label": "Unit",
            "name": "Vampire Lord",
            "text": "Vampire Lord, Lord choice...",
            "source_url": "https://tow.whfb.app/unit/vampire-lord",
        },
        {
            "id": "nightshroud",
            "label": "MagicItem",
            "name": "Nightshroud",
            "text": "Magic armour that reduces enemy Strength...",
            "source_url": "https://tow.whfb.app/magic-items/nightshroud",
        },
    ]
    context = (
        "## Retrieved sources\n"
        "- [vampire-lord] Vampire Lord (Unit): Lord choice for Vampire Counts.\n"
        "- [nightshroud] Nightshroud (MagicItem): Magic armour.\n\n"
        "## Direct links among sources\n"
        "- [vampire-lord] --CAN_TAKE_ITEM--> [nightshroud]"
    )
    tool_call_id = "example_call_eligibility"
    return [
        HumanMessage(content="Can a Vampire Lord take the Nightshroud armour?"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "query_warhammer_archive",
                    "args": {"query": query},
                    "id": tool_call_id,
                }
            ],
        ),
        ToolMessage(
            content=_tool_result(context, sources),
            tool_call_id=tool_call_id,
            name="query_warhammer_archive",
        ),
        AIMessage(
            content=(
                "Yes. The Vampire Lord can take the Nightshroud because there is a "
                "`CAN_TAKE_ITEM` edge from [vampire-lord] to [nightshroud]."
            ),
        ),
    ]


def _army_list_example() -> list[AnyMessage]:
    """Example: building a small Vampire Counts core."""
    first_query = "vampire-counts core units points"
    first_sources = [
        {
            "id": "skeleton-warriors",
            "label": "Unit",
            "name": "Skeleton Warriors",
            "text": "Core infantry, 5 pts/model...",
            "source_url": "https://tow.whfb.app/unit/skeleton-warriors",
        },
        {
            "id": "dire-wolves",
            "label": "Unit",
            "name": "Dire Wolves",
            "text": "Core cavalry, 8 pts/model...",
            "source_url": "https://tow.whfb.app/unit/dire-wolves",
        },
    ]
    first_context = (
        "## Retrieved sources\n"
        "- [skeleton-warriors] Skeleton Warriors (Unit): Core infantry, 5 pts/model.\n"
        "- [dire-wolves] Dire Wolves (Unit): Core cavalry, 8 pts/model."
    )
    first_call_id = "example_call_army_1"

    second_query = "skeleton-warriors unit size points"
    second_sources = [
        {
            "id": "skeleton-warriors",
            "label": "Unit",
            "name": "Skeleton Warriors",
            "text": "Core infantry, 5 pts/model, unit size 10+.",
            "source_url": "https://tow.whfb.app/unit/skeleton-warriors",
        }
    ]
    second_context = (
        "## Retrieved sources\n"
        "- [skeleton-warriors] Skeleton Warriors (Unit): Core infantry, "
        "5 pts/model, unit size 10+."
    )
    second_call_id = "example_call_army_2"

    return [
        HumanMessage(content="Suggest a 1000 point Vampire Counts core section."),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "query_warhammer_archive",
                    "args": {"query": first_query},
                    "id": first_call_id,
                }
            ],
        ),
        ToolMessage(
            content=_tool_result(first_context, first_sources),
            tool_call_id=first_call_id,
            name="query_warhammer_archive",
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "query_warhammer_archive",
                    "args": {"query": second_query},
                    "id": second_call_id,
                }
            ],
        ),
        ToolMessage(
            content=_tool_result(second_context, second_sources),
            tool_call_id=second_call_id,
            name="query_warhammer_archive",
        ),
        AIMessage(
            content=(
                "For a 1000 point Vampire Counts core, consider:\n"
                "- 40 Skeleton Warriors (200 pts) [skeleton-warriors]\n"
                "- 10 Dire Wolves (80 pts) [dire-wolves]\n\n"
                "This leaves room for characters and rare choices."
            ),
        ),
    ]


def build_few_shot_messages() -> list[AnyMessage]:
    """Return few-shot example turns to prepend to the conversation."""
    messages: list[AnyMessage] = []
    messages.extend(_rule_interaction_example())
    messages.extend(_eligibility_example())
    messages.extend(_army_list_example())
    return messages
