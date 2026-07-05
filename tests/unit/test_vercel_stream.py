"""Direct tests for the VercelStream adapter.

These bypass the FastAPI app and the LangGraph agent so we can assert exact
behaviour of the SSE formatting, especially the filtering of source chips to
only those cited by the model.
"""

from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator

import pytest
from langchain.messages import AIMessageChunk, ToolMessage

from backend.api.vercel_stream import VercelStream


def _parse_sse_events(body: str) -> list[dict[str, Any]]:
    """Parse a raw SSE body string into a list of JSON payloads."""
    events = []
    for line in body.strip().split("\n\n"):
        match = re.match(r"^data:\s*(.+)$", line.strip())
        if match:
            events.append(json.loads(match.group(1)))
    return events


async def _scripted_stream(
    messages: list[Any],
) -> AsyncIterator[tuple[Any, dict[str, Any]]]:
    """Yield (message, metadata) pairs for VercelStream."""
    for msg in messages:
        yield msg, {}


async def _collect_stream(messages: list[Any]) -> list[dict[str, Any]]:
    """Run VercelStream over scripted messages and return parsed events."""
    chunks = [
        chunk async for chunk in VercelStream.stream_langgraph(_scripted_stream(messages))
    ]
    return _parse_sse_events("".join(chunks))


def _source(id_: str, **kwargs: Any) -> dict[str, Any]:
    """Build a source dict with required keys."""
    return {
        "id": id_,
        "label": kwargs.get("label", "SpecialRule"),
        "name": kwargs.get("name", id_.replace("-", " ").title()),
        "text": kwargs.get("text", "..."),
        "source_url": kwargs.get("source_url", f"https://tow.whfb.app/{id_}"),
    }


@pytest.mark.asyncio
async def test_emits_only_cited_sources() -> None:
    """Only sources whose ids appear as [slug] in the answer become chips."""
    events = await _collect_stream(
        [
            AIMessageChunk(
                content="",
                tool_calls=[
                    {
                        "name": "query_warhammer_archive",
                        "args": {"query": "stubborn"},
                        "id": "call_1",
                    }
                ],
            ),
            ToolMessage(
                content=json.dumps(
                    {
                        "context": "Fake context",
                        "sources": [
                            _source("stubborn"),
                            _source("fear"),
                        ],
                    }
                ),
                tool_call_id="call_1",
                name="query_warhammer_archive",
            ),
            AIMessageChunk(
                content="Stubborn units ignore Combat Result modifiers [stubborn]."
            ),
        ]
    )

    types = [e["type"] for e in events]
    assert types == ["text-start", "text-delta", "text-end", "data-sources", "finish-step"]

    source_event = events[3]
    data = source_event["data"]
    assert len(data) == 1
    assert data[0]["id"] == "stubborn"
    assert not any(item["id"] == "fear" for item in data)


@pytest.mark.asyncio
async def test_emits_empty_data_sources_when_nothing_cited() -> None:
    """If the model answers without citing any source, emit an empty list."""
    events = await _collect_stream(
        [
            AIMessageChunk(
                content="",
                tool_calls=[
                    {
                        "name": "query_warhammer_archive",
                        "args": {"query": "stubborn"},
                        "id": "call_1",
                    }
                ],
            ),
            ToolMessage(
                content=json.dumps(
                    {
                        "context": "Fake context",
                        "sources": [_source("stubborn"), _source("fear")],
                    }
                ),
                tool_call_id="call_1",
                name="query_warhammer_archive",
            ),
            AIMessageChunk(content="I don't have enough information to answer that."),
        ]
    )

    source_event = next(e for e in events if e["type"] == "data-sources")
    assert source_event["data"] == []


@pytest.mark.asyncio
async def test_drops_hallucinated_citations() -> None:
    """A citation not present in the retrieved sources must not produce a chip."""
    events = await _collect_stream(
        [
            AIMessageChunk(
                content="",
                tool_calls=[
                    {
                        "name": "query_warhammer_archive",
                        "args": {"query": "stubborn"},
                        "id": "call_1",
                    }
                ],
            ),
            ToolMessage(
                content=json.dumps(
                    {
                        "context": "Fake context",
                        "sources": [_source("stubborn")],
                    }
                ),
                tool_call_id="call_1",
                name="query_warhammer_archive",
            ),
            AIMessageChunk(content="See [stubborn] and [made-up-rule]."),
        ]
    )

    source_event = next(e for e in events if e["type"] == "data-sources")
    assert len(source_event["data"]) == 1
    assert source_event["data"][0]["id"] == "stubborn"


@pytest.mark.asyncio
async def test_no_data_sources_when_no_tool_call() -> None:
    """A plain text turn without tool calls must not emit a data-sources event."""
    events = await _collect_stream(
        [
            AIMessageChunk(content="Hello "),
            AIMessageChunk(content="world!"),
        ]
    )

    types = [e["type"] for e in events]
    assert "data-sources" not in types
    assert types == ["text-start", "text-delta", "text-delta", "text-end", "finish-step"]


@pytest.mark.asyncio
async def test_bracket_noise_does_not_match_candidates() -> None:
    """Stat notation like [D3] or [X+] should not be mistaken for citations."""
    events = await _collect_stream(
        [
            AIMessageChunk(
                content="",
                tool_calls=[
                    {
                        "name": "query_warhammer_archive",
                        "args": {"query": "stubborn"},
                        "id": "call_1",
                    }
                ],
            ),
            ToolMessage(
                content=json.dumps(
                    {
                        "context": "Fake context",
                        "sources": [
                            _source("d3", label="SpecialRule"),
                            _source("x", label="SpecialRule"),
                        ],
                    }
                ),
                tool_call_id="call_1",
                name="query_warhammer_archive",
            ),
            AIMessageChunk(content="Roll [D3] wounds at Strength [X+]."),
        ]
    )

    source_event = next(e for e in events if e["type"] == "data-sources")
    assert source_event["data"] == []
