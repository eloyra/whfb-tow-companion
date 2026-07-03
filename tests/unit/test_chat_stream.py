"""Smoke tests for the chat SSE streaming protocol."""

import json
import re
from typing import Any, ClassVar

import pytest
from httpx import ASGITransport, AsyncClient
from langchain.chat_models import BaseChatModel
from langchain.messages import AIMessageChunk, AnyMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult

from backend.api.dependencies import get_llm, get_rag_pipeline
from backend.api.main import app


class FakeChatModel(BaseChatModel):
    """Fake LLM that yields hardcoded AIMessageChunk tokens via _astream."""

    chunks: ClassVar[list[AIMessageChunk]] = []
    call_count: ClassVar[int] = 0

    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError

    async def _agenerate(self, *args: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError

    async def _astream(
        self,
        messages: list[AnyMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ):
        FakeChatModel.call_count += 1
        for chunk in FakeChatModel.chunks:
            yield ChatGenerationChunk(message=chunk)

    def bind_tools(self, tools: list, **kwargs: Any) -> "FakeChatModel":
        return self


class FakeRAGPipeline:
    """Fake GraphRAG pipeline that returns a deterministic tool result."""

    def query(self, query: str) -> dict:
        return {
            "context": f"Fake context for: {query}",
            "sources": [
                {
                    "id": "stubborn",
                    "label": "SpecialRule",
                    "name": "Stubborn",
                    "text": "Stubborn units ignore Combat Result modifiers when testing Break.",
                    "url": "https://tow.whfb.app/special-rules/stubborn",
                    "score": 0.95,
                }
            ],
            "links": [],
            "expansion": [],
        }


def _parse_sse_events(body: str) -> list[dict]:
    """Parse a raw SSE body string into a list of JSON payloads."""
    events = []
    for line in body.strip().split("\n\n"):
        match = re.match(r"^data:\s*(.+)$", line.strip())
        if match:
            events.append(json.loads(match.group(1)))
    return events


def _build_client():
    """Build an httpx AsyncClient attached to the FastAPI app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def _reset_fake():
    """Reset FakeChatModel state before each test."""
    FakeChatModel.chunks = []
    FakeChatModel.call_count = 0

    app.dependency_overrides[get_llm] = lambda: FakeChatModel()
    app.dependency_overrides[get_rag_pipeline] = lambda: FakeRAGPipeline()
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_stream_yields_expected_events():
    """Plain text turn: SSE must contain text-start, deltas, text-end, finish-step."""
    FakeChatModel.chunks = [
        AIMessageChunk(content="Hello"),
        AIMessageChunk(content=" world!"),
    ]

    async with _build_client() as client:
        response = await client.post(
            "/chat/",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "Hello"}]}]},
            headers={"x-vercel-ai-ui-message-stream": "v1"},
        )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)

    types = [e["type"] for e in events]
    assert "text-start" in types
    assert "text-delta" in types
    assert "text-end" in types
    assert "finish-step" in types

    # Events must appear in correct order
    start_idx = types.index("text-start")
    delta_idxs = [i for i, t in enumerate(types) if t == "text-delta"]
    end_idx = types.index("text-end")
    finish_idx = types.index("finish-step")

    assert start_idx < min(delta_idxs)
    assert max(delta_idxs) < end_idx
    assert end_idx < finish_idx


@pytest.mark.asyncio
async def test_chat_stream_emits_data_sources_on_tool_call():
    """Tool turn: SSE must emit a data-sources event with a flat array of node dicts."""
    FakeChatModel.chunks = [
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
    ]

    async with _build_client() as client:
        response = await client.post(
            "/chat/",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "Stubborn?"}]}]},
            headers={"x-vercel-ai-ui-message-stream": "v1"},
        )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)

    data_events = [
        e for e in events if isinstance(e.get("type"), str) and e["type"].startswith("data-")
    ]
    assert len(data_events) >= 1, f"No data-* event found in {[e['type'] for e in events]}"

    source_event = data_events[0]
    assert source_event["type"] == "data-sources"
    data = source_event["data"]
    assert isinstance(data, list), f"Expected flat list, got {type(data)}"
    assert len(data) > 0
    for item in data:
        assert isinstance(item, dict), f"Expected list of dicts, found {type(item)} in {data}"
        assert "id" in item
        assert "source_url" in item
        assert item["source_url"] == "https://tow.whfb.app/special-rules/stubborn"
