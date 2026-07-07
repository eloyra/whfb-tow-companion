"""Tests for the few-shot example messages."""

from __future__ import annotations

import json

from langchain.messages import AIMessage, HumanMessage, ToolMessage

from backend.rag.prompts.few_shot import build_few_shot_messages


def test_build_few_shot_messages_returns_complete_examples() -> None:
    """The helper should return all three example cycles."""
    messages = build_few_shot_messages()
    assert len(messages) == 14  # 4 + 4 + 6 messages across three examples

    # Every example starts with a human question.
    assert isinstance(messages[0], HumanMessage)
    assert isinstance(messages[4], HumanMessage)
    assert isinstance(messages[8], HumanMessage)


def test_few_shot_tool_calls_match_tool_messages() -> None:
    """Each AIMessage tool_call must have a matching ToolMessage."""
    messages = build_few_shot_messages()
    tool_call_ids: list[str] = []
    tool_message_ids: list[str] = []

    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            tool_call_ids.extend(tc["id"] for tc in msg.tool_calls)
        elif isinstance(msg, ToolMessage):
            tool_message_ids.append(msg.tool_call_id)

    assert tool_call_ids
    assert set(tool_call_ids) == set(tool_message_ids)


def test_few_shot_final_answers_contain_citations() -> None:
    """Every example should end with an assistant answer that cites sources."""
    messages = build_few_shot_messages()
    final_answers = [
        msg for msg in messages if isinstance(msg, AIMessage) and not msg.tool_calls
    ]
    assert len(final_answers) == 3
    for answer in final_answers:
        assert "[" in answer.content and "]" in answer.content


def test_rule_interaction_example_cites_flammable_not_overgeneralises() -> None:
    """Example A must state the Flammable condition and cite flammable.

    This is a regression guard against an earlier version that incorrectly
    taught "Flaming Attacks cancel Regeneration" and cited the wrong sources.
    """
    messages = build_few_shot_messages()

    # Example A is the first 4 messages: Human, AI tool call, Tool, AI answer.
    assert isinstance(messages[2], ToolMessage)
    tool_result = json.loads(messages[2].content)
    source_ids = {src["id"] for src in tool_result["sources"]}
    assert "flammable" in source_ids, "flammable must be present as a seed source"

    assert isinstance(messages[3], AIMessage)
    answer = messages[3].content
    assert "[flammable]" in answer, "answer must cite the decisive flammable source"
    assert "cancel Regeneration" not in answer, "answer must not over-generalise"
    assert "Flammable special rule" in answer, "answer must state the condition"
