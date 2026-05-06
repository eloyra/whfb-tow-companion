# Plan — Migrate backend to LangGraph (`create_react_agent` + tool calling)

## Context

Today the chat backend uses LangChain directly:
- `backend/api/routes/chat.py` builds a list of `HumanMessage`/`AIMessage`/`SystemMessage` and calls `llm.astream(...)` to get raw token chunks.
- `backend/api/vercel_stream.py` adapts those chunks into the Vercel AI SDK v6 UI Message Stream Protocol (SSE).

There is no agentic loop, no tools, and no place to plug GraphRAG retrieval. As soon as we want the assistant to consult the Neo4j graph, we have to either roll a manual ReAct loop or migrate to a framework that already does it.

This plan replaces the manual chain with **LangGraph's `create_react_agent`**, switches streaming to `stream_mode="messages"` (which yields `(message_chunk, metadata)` tuples), and updates `VercelStream` to handle both `AIMessageChunk` (for text) and `ToolMessage` (for tool results forwarded to the frontend as Vercel `data` events). It also lays a thin scaffold for the real GraphRAG tool to be wired in later, without coupling the route to its implementation.

The migration is contained: only three files change, the dependency footprint shrinks slightly, and the public API contract (`POST /chat`, the SSE shape, the `x-vercel-ai-ui-message-stream: v1` header) is preserved so the frontend keeps working unchanged.

## Scope

In scope (backend bounded context only):
1. Dependency swap in `pyproject.toml`.
2. Rewrite `backend/api/vercel_stream.py` for LangGraph messages mode.
3. Rewrite `backend/api/routes/chat.py` to use `create_react_agent`.
4. Extract the system prompt and the (mock for now) tool into dedicated modules under `backend/rag/` so the route stays thin and the tool can be replaced with the real GraphRAG retriever later without touching the API layer.
5. Add a minimal pytest covering the streaming protocol so future regressions surface.

Out of scope: frontend changes, real Neo4j GraphRAG implementation, persistent agent memory / checkpointers, the `/graph` routes, the unused `backend/llm/client.py` Protocol stubs.

## Files to change

| File | Action |
|---|---|
| `pyproject.toml` | Edit dependencies |
| `backend/api/vercel_stream.py` | Rewrite |
| `backend/api/routes/chat.py` | Rewrite |
| `backend/rag/prompts/system_prompt.py` | Implement (currently `# TODO` stub) |
| `backend/rag/tools.py` | New file — mock GraphRAG tool |
| `tests/unit/test_chat_stream.py` | New file — minimal SSE smoke test |

Untouched: `backend/api/main.py`, `backend/api/dependencies.py`, `backend/api/routes/graph.py`, `backend/llm/*`, all `backend/rag/*` other than the two listed above.

---

## Step 1 — Dependencies (`pyproject.toml`)

Current `[project].dependencies` (lines 23–25) and `[project.optional-dependencies].dev` (line 50) include:

- `langchain>=0.2.0`
- `langchain-community>=0.2.0`
- `langchain-openai>=0.1.0`
- `langchain-ollama>=1.1.0` (dev)

Neither `langchain` nor `langchain-community` are imported anywhere in `backend/`, `pipeline/`, or `tests/` (verified by grep — only `langchain_core`, `langchain_openai`, `langchain_ollama` are used). Drop them.

**Final state:**

```toml
# in [project].dependencies, replace the three langchain* lines with:
"langchain-core>=0.3.0",
"langchain-openai>=0.2.0",
"langgraph>=0.2.0",
```

```toml
# in [project.optional-dependencies].dev, keep:
"langchain-ollama>=1.1.0",
```

Notes:
- Pin `langchain-core` explicitly: `create_react_agent` and `VercelStream` both import from it directly; do not rely on transitive resolution.
- `langchain-ollama` stays in `dev` because Ollama is the local-dev provider; if it is needed in prod, promote it to main deps in a separate change — not part of this migration.
- After editing, refresh the lockfile with `uv lock` and install with `uv sync --extra dev`.

---

## Step 2 — Rewrite `backend/api/vercel_stream.py`

LangGraph's `agent.astream(..., stream_mode="messages")` yields `(message, metadata)` tuples where `message` is one of:
- `AIMessageChunk` — token-by-token output from the LLM. Stream as `text-delta`.
- `ToolMessage` — the result of a tool call. Forward as a Vercel `data` event so the frontend can render citations / sources.
- Other internal message types (e.g. `HumanMessage` echoes, `AIMessage` non-chunk wrappers) — ignore.

Key differences from current `stream_langchain`:
- Iteration unpacks a tuple, not a single chunk.
- `AIMessageChunk.content` may be a list (multimodal) or a string. Only stream when it is a non-empty string.
- New branch for `ToolMessage`: parse `msg.content` as JSON; if it parses, emit `{"type": "data", "data": [tool_data]}`; otherwise silently skip (robust against future free-text tools).

**Replacement file** (full body):

```python
import json
import uuid
from typing import AsyncIterator, Any

from langchain_core.messages import AIMessageChunk, ToolMessage


class VercelStream:
    """
    Adapts a LangGraph `stream_mode="messages"` stream into the Vercel AI SDK v6
    UI Message Stream Protocol (SSE). The frontend reads this via the
    `x-vercel-ai-ui-message-stream: v1` header.
    """

    @staticmethod
    async def stream_langgraph(agent_stream: AsyncIterator[Any]) -> AsyncIterator[str]:
        msg_id = f"msg_{uuid.uuid4().hex}"

        yield f"data: {json.dumps({'type': 'text-start', 'id': msg_id})}\n\n"

        try:
            async for msg, _metadata in agent_stream:
                if isinstance(msg, AIMessageChunk):
                    if msg.content and isinstance(msg.content, str):
                        yield f"data: {json.dumps({'type': 'text-delta', 'id': msg_id, 'delta': msg.content})}\n\n"

                elif isinstance(msg, ToolMessage):
                    try:
                        tool_data = json.loads(msg.content)
                    except (TypeError, ValueError):
                        continue
                    yield f"data: {json.dumps({'type': 'data', 'data': [tool_data]})}\n\n"

            yield f"data: {json.dumps({'type': 'text-end', 'id': msg_id})}\n\n"
            yield f"data: {json.dumps({'type': 'finish-step'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'value': str(e)})}\n\n"
```

Notes for the implementer:
- Drop the old `stream_langchain` method entirely. Its only caller (`chat.py`) is also being rewritten.
- Catch `(TypeError, ValueError)` specifically — bare `except` would swallow `KeyboardInterrupt`/`SystemExit`.

---

## Step 3 — Extract system prompt and tool

### `backend/rag/prompts/system_prompt.py` (currently `# TODO` stub)

```python
"""System prompt for the chat agent."""

SYSTEM_PROMPT = (
    "You are an expert assistant on Warhammer: The Old World, a tabletop wargame "
    "by Games Workshop. Answer questions about rules, units, magic items, special "
    "rules, and army composition. "
    "When you use information returned by a tool, cite the source by including "
    "the node id in square brackets, e.g. [blood-knights]. "
    "If the user writes in Spanish, reply in Spanish; otherwise reply in English."
)
```

### `backend/rag/tools.py` (new file)

A single mock tool so the agent has something to call now. Replace the body with the real Neo4j retriever later — the route never has to change.

```python
"""Tools exposed to the chat agent. Replace mocks with real GraphRAG calls later."""

import json

from langchain_core.tools import tool


@tool
def query_warhammer_archive(query: str) -> str:
    """Query the Warhammer: The Old World knowledge graph for rules, units, magic
    items, special rules, and lore. Use this tool whenever the user asks a factual
    question about the game. Returns a JSON array of matching nodes; cite the `id`
    field of any node you use.
    """
    mock_nodes = [
        {"id": "great-swords", "text": "Great Swords have the Stubborn special rule."},
        {"id": "stubborn", "text": "Stubborn units ignore Combat Result modifiers when testing Break."},
    ]
    return json.dumps(mock_nodes)


AGENT_TOOLS = [query_warhammer_archive]
```

Notes:
- `AGENT_TOOLS` is the export point. The route imports the list; adding a second tool is a one-line change here.
- The tool docstring is LLM-visible. Keep it imperative ("Use this tool whenever…") to bias the agent toward calling it.

---

## Step 4 — Rewrite `backend/api/routes/chat.py`

**Replacement file** (full body):

```python
from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

from backend.api.dependencies import get_llm
from backend.api.vercel_stream import VercelStream
from backend.rag.prompts.system_prompt import SYSTEM_PROMPT
from backend.rag.tools import AGENT_TOOLS

router = APIRouter()


class MessagePart(BaseModel):
    type: str
    text: str


class Message(BaseModel):
    role: str
    id: Optional[str] = None
    parts: Optional[List[MessagePart]] = None

    @property
    def text_content(self) -> str:
        if not self.parts:
            return ""
        return "".join(part.text for part in self.parts if part.type == "text")


class ChatRequest(BaseModel):
    messages: List[Message]


@router.post("/")
async def chat(
    request: ChatRequest,
    llm: BaseChatModel = Depends(get_llm),
) -> StreamingResponse:
    lc_messages = [SystemMessage(content=SYSTEM_PROMPT)]
    for msg in request.messages:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.text_content))
        elif msg.role == "assistant":
            lc_messages.append(AIMessage(content=msg.text_content))
        elif msg.role == "system":
            lc_messages.append(SystemMessage(content=msg.text_content))

    agent = create_react_agent(llm, tools=AGENT_TOOLS)
    agent_stream = agent.astream({"messages": lc_messages}, stream_mode="messages")

    return StreamingResponse(
        VercelStream.stream_langgraph(agent_stream),
        media_type="text/event-stream",
        headers={"x-vercel-ai-ui-message-stream": "v1"},
    )
```

Notes:
- `Message`, `MessagePart`, `ChatRequest`, and `text_content` keep the same shape — frontend payload contract unchanged.
- Building `agent` per request is intentional: `create_react_agent` is cheap and stateless; a module-level singleton would couple it to a single LLM instance and break `Depends(get_llm)`.

---

## Step 5 — Minimal regression test (`tests/unit/test_chat_stream.py`)

Today there are zero tests covering the chat route. Add one focused async test that:
1. Builds a fake `BaseChatModel` whose `astream` yields two `AIMessageChunk`s.
2. Overrides `get_llm` via `app.dependency_overrides`.
3. Posts to `/chat` with `httpx.AsyncClient`.
4. Asserts the SSE body contains `text-start`, `text-delta`, `text-end`, and `finish-step` events in order.

`pyproject.toml` already has `asyncio_mode = "auto"` so no extra config is needed. `httpx` is already in the dependency tree via FastAPI; if not, add it to dev deps.

---

## Verification

After implementing, run in order:

1. `uv lock && uv sync --extra dev` — confirm `langchain` and `langchain-community` are gone from the tree (`uv tree | grep langchain`).
2. `make lint` — no new ruff violations.
3. `make test` — new test passes, nothing else regresses.
4. **Manual smoke — plain text turn:** `make serve` → send "Hello". Expected SSE: `text-start`, several `text-delta`, `text-end`, `finish-step`. No `data` events.
5. **Manual smoke — rules question:** send "What does Stubborn do?". Expected SSE: at least one `data` event carrying the mock node array, plus normal text events.

---

## Decisions

- **System prompt in English** — per `CLAUDE.md` "Language" rule; the mock's Spanish prompt was not adopted. An `"answer in user's language"` instruction preserves Spanish support at runtime without storing Spanish in source.
- **Legacy `backend/llm/client.py`** — verified zero importers; left untouched here. Flag for removal in a separate cleanup PR.
- **No checkpointer / persistent memory** — `create_react_agent` is stateless per request; conversation history comes from the frontend payload (existing behavior). Adding `MemorySaver` is a follow-up, not part of this change.
