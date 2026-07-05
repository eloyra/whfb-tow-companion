"""Tests for the few-shot example messages."""

from __future__ import annotations

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
