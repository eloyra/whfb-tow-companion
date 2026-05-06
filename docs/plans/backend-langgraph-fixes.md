# Plan — Fix LangGraph chat streaming bugs

## Context

After the LangGraph migration (`docs/plans/backend-langgraph-migration.md`), the chat works for plain text turns but **crashes the frontend whenever the agent calls a tool**. The Vercel AI SDK v6 client validates every incoming SSE event against a Zod union of UI message-stream parts; the backend currently emits a shape that does not match any variant, the validation throws `AI_TypeValidationError`, and the SDK surfaces the error as a chat bubble in the UI.

This plan fixes the protocol violation, removes the double-wrapped payload, and addresses the smaller follow-ups left open by the previous review (tooling test coverage, fake LLM streaming path, redundant isinstance check).

Scope is backend only. The frontend already filters unknown part types silently (`ChatInterface.tsx:151`) so once the backend emits valid parts, no UI change is needed.

---

## Root causes

### Bug 1 — invalid event type (`"data"` is not a Vercel UI part)

`backend/api/vercel_stream.py:37` emits:

```json
{"type": "data", "data": [tool_data]}
```

The Vercel AI SDK v6 UI Message Stream Protocol does not have a plain `"data"` variant. Custom data parts must use a **`data-<name>` discriminator**, e.g. `"data-sources"`, `"data-warhammer-nodes"`. The Zod union the SDK ships with includes `text-start`, `text-delta`, `text-end`, `error`, `tool-input-*`, `tool-output-*`, `tool-approval-request`, `reasoning-*`, and `data-${string}` — nothing matches `"data"` exactly, so validation fails on the first tool turn.

### Bug 2 — payload double-wrapped

`@tool` returns a JSON string of an array; the stream loads it back into a list (`tool_data` is already `list[dict]`) and then wraps it again in a one-element list:

```python
yield ... 'data': [tool_data] ...   # → [[{"id": "great-swords", ...}, ...]]
```

The error log confirms: `value: { type: 'data', data: [ [Array] ] }` — array nested inside array. Even after fixing the type, the consumer expects a flat array of node objects, not `array<array<node>>`.

### Bug 3 — frontend renders the validation error as a chat message

The `useChat` hook's `onError` callback only logs (`ChatInterface.tsx:22`), but the `<Alert>` block (`ChatInterface.tsx:52-69`) reads `error.message` from the hook state and renders the full Zod failure dump. Once Bug 1 is fixed the alert disappears on its own — no frontend change required.

### Tooling debt (carried over from prior review)

- `vercel_stream.py:23` accepts `(AIMessageChunk, AIMessage)`. `AIMessageChunk` subclasses `AIMessage`, so the tuple is redundant. Worse, if a real model ever yields both a streamed chunk sequence and a finalising `AIMessage` for the same turn (some LangGraph internal transitions can do this), the body would be **streamed twice**.
- `tests/unit/test_chat_stream.py` exercises only the `_agenerate` (non-streaming) path because `FakeChatModel` does not override `_astream`. The chunked branch and the `ToolMessage` branch have no coverage.

---

## Fixes

### Fix 1 — Emit valid Vercel `data-*` parts (`backend/api/vercel_stream.py`)

Switch to a typed data part. Two viable shapes; we adopt **option A** (custom `data-sources`) because it requires no LangGraph metadata threading and matches how the frontend will eventually render citations.

**Before:**

```python
elif isinstance(msg, ToolMessage):
    try:
        tool_data = json.loads(msg.content)
    except (TypeError, ValueError):
        continue
    yield f"data: {json.dumps({'type': 'data', 'data': [tool_data]})}\n\n"
```

**After:**

```python
elif isinstance(msg, ToolMessage):
    try:
        tool_data = json.loads(msg.content)
    except (TypeError, ValueError):
        continue
    payload = {
        "type": "data-sources",
        "id": msg.tool_call_id or f"sources_{uuid.uuid4().hex}",
        "data": tool_data,
    }
    yield f"data: {json.dumps(payload)}\n\n"
```

Notes:
- Type is `"data-sources"` (frontend can later render citations from this stream). The exact slug after `data-` is the contract between backend and frontend; pick once and stick to it. If a different name fits the UI better (`data-citations`, `data-warhammer-nodes`), change consistently.
- `data` field carries the parsed tool result directly — no extra wrapping list.
- `id` enables the Vercel SDK to reconcile updates if the same tool is called multiple times. `ToolMessage.tool_call_id` is set by `create_react_agent`; fall back to a UUID if missing.

### Fix 2 — Remove redundant `AIMessage` from isinstance, override fake's stream path

`backend/api/vercel_stream.py:23`:

```python
if isinstance(msg, AIMessageChunk):   # was: (AIMessageChunk, AIMessage)
```

And drop the `AIMessage` import. `stream_mode="messages"` yields chunks only for streaming-capable models. If a non-streaming model is ever used, fix it in the fake (below) — not by widening the production isinstance check.

`tests/unit/test_chat_stream.py` — add an `_astream` override on `FakeChatModel` so the test exercises the real chunk path:

```python
async def _astream(
    self,
    messages: list[BaseMessage],
    stop: list[str] | None = None,
    run_manager: Any = None,
    **kwargs: Any,
):
    for chunk in FakeChatModel.chunks:
        yield ChatGenerationChunk(message=chunk)
```

(`ChatGenerationChunk` lives in `langchain_core.outputs`.) Existing `_agenerate` can stay as a safety net but the smoke test now covers the streaming branch.

### Fix 3 — Add a tool-flow regression test

New test in `tests/unit/test_chat_stream.py` (or a sibling `test_chat_tool_stream.py`):

1. Build a fake model that returns one `AIMessageChunk` with `tool_call_chunks` calling `query_warhammer_archive`, then on the second invocation returns a final `AIMessageChunk("Done.")`.
2. POST to `/chat/`.
3. Assert the SSE body contains exactly one event whose type starts with `"data-"`, whose `data` field is a list of dicts each having an `id` key. Assert the type is `"data-sources"`.
4. Assert `data` is **not** a nested list (`isinstance(event["data"], list) and isinstance(event["data"][0], dict)`).

This guards against the exact regression we are fixing.

---

## Optional follow-up (not part of this fix, flagged for visibility)

The current shape lets us forward tool *results* but not the tool *call itself*. Vercel's SDK has a richer flow:
- `tool-input-start` when the LLM begins emitting `tool_call_chunks`.
- `tool-input-delta` per arg-token.
- `tool-input-available` when args are complete.
- `tool-output-available` when `ToolMessage` arrives.

If we want the UI to show "Calling `query_warhammer_archive` with `query=…`" before the result lands (typical Vercel chat UX), we will need to read `AIMessageChunk.tool_call_chunks` and emit those four event types. That is bigger than this bugfix and should land as a separate change once we have a real GraphRAG tool to justify the UX.

---

## Files to change

| File | Action |
|---|---|
| `backend/api/vercel_stream.py` | Edit — fix Bug 1 + Bug 2, drop redundant `AIMessage` |
| `tests/unit/test_chat_stream.py` | Edit — add `_astream` to fake; add tool-flow test |

Untouched: `backend/api/routes/chat.py`, `backend/rag/tools.py`, `backend/rag/prompts/system_prompt.py`, `pyproject.toml`, frontend.

---

## Verification

1. `make lint` — clean.
2. `make test` — both new tests pass; existing test still green.
3. **Manual smoke against real LLM** (the step skipped after the migration):
   - `make serve`
   - Frontend chat: ask "Hello" → expect plain text reply, no error alert.
   - Frontend chat: ask "What does Stubborn do?" → expect text reply citing `[great-swords]` / `[stubborn]`. **No `AI_TypeValidationError` alert.** Network panel: at least one SSE event with `type: "data-sources"` and a flat `data: [{...}, {...}]` array.
4. Quick sanity check that the prior duplicate-streaming risk is not real: in the same smoke test, confirm assistant message text is not duplicated. If it is, the `AIMessageChunk` isinstance is matching twice and we need to investigate where the second emit comes from.
