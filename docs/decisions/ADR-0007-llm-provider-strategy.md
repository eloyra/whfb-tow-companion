# ADR-0007 — LLM Provider Strategy

| Field       | Value                          |
|-------------|--------------------------------|
| **Status**  | Accepted                       |
| **Date**    | 2026-07-03                     |
| **Deciders**| Project author                 |
| **Tags**    | backend, llm, rag, dependencies |

---

## Context

The backend has two parallel LLM-resolution mechanisms:

1. `backend/llm/client.py` — a `LLMClient` Protocol plus a `get_llm_client()` dispatcher
   that imports provider submodules (`_openai.py`, `_anthropic.py`, `_local.py`).
   `backend/CLAUDE.md` (pre-amendment) documented this as the canonical path. In practice
   all three submodules are `# TODO` stubs, so `get_llm_client()` raises at call time, and
   nothing in the application imports it.
2. `backend/api/dependencies.py::get_llm()` — a FastAPI dependency that instantiates a
   LangChain `BaseChatModel` (`ChatOllama` or `ChatOpenAI`) from `LLM_PROVIDER` /
   `LLM_MODEL` / `OPENAI_API_KEY`. This is the path the live `/chat` route actually uses:
   `routes/chat.py` passes the result to `langchain.agents.create_agent`, which requires a
   `BaseChatModel`.

The two paths also disagree on defaults (`llm/client.py` defaults to `"openai"`;
`dependencies.get_llm()` defaults to `"ollama"`) and on Anthropic support (the Protocol
lists it; `get_llm()` has no Anthropic branch).

This divergence must be resolved before the RAG layer is built, so that `rag/pipeline.py`,
retrieval tools, and tests all resolve the LLM the same way the working `/chat` route does.

---

## Decision

**Canonical LLM resolution is `api/dependencies.py::get_llm()`**, returning a LangChain
`BaseChatModel`. All backend code (routes, RAG pipeline, tools, tests) obtains the LLM via
`Depends(get_llm)` or by calling `get_llm()` directly. Never import or instantiate a
provider chat model ad hoc.

`backend/llm/client.py` and the three provider submodules (`_openai.py`, `_anthropic.py`,
`_local.py`) are **deprecated**. Do not add new code to them. They may be removed in a
follow-up cleanup; they are retained only as a historical artefact until the RAG layer is
in place.

### Providers

- **Ollama** (default when `LLM_PROVIDER=local` or unset) — via `ChatOllama`. Suitable for
  local inference (Ollama at `LOCAL_LLM_BASE_URL`).
- **OpenAI** (`LLM_PROVIDER=openai`) — via `ChatOpenAI`.
- **Anthropic** (`LLM_PROVIDER=anthropic`) — **known gap**. `get_llm()` has no Anthropic
  branch yet. Adding it (`ChatAnthropic`) is a small follow-up task; until then, Anthropic
  is documented as unsupported on the live path even though the root `.env` advertises it.

### Why LangChain chat models, not a custom Protocol

`create_agent` (LangGraph) consumes a `BaseChatModel` directly. Wrapping providers behind a
custom `LLMClient` Protocol would require an adapter to satisfy `BaseChatModel`, adding
indirection for no behavioural gain. LangChain already abstracts provider differences
(streaming, tool-calling) behind a stable interface, which is exactly what the deprecated
Protocol attempted to reinvent.

---

## Consequences

### Positive

- One LLM-resolution path, matching the only working route (`/chat`).
- `rag/pipeline.py` and tests can reuse `get_llm()` without a second abstraction.
- Tool-calling and streaming behave consistently because they come from LangChain's
  `BaseChatModel` contract, not a hand-rolled wrapper.

### Negative / accepted trade-offs

- Anthropic is not wired into the live path yet (tracked as a follow-up).
- `llm/client.py` and the three stub files remain as dead code until a cleanup pass removes
  them. This is preferable to deleting now and losing the historical context before the RAG
  layer lands.
- Provider-specific tunables (e.g. timeout, retry) must be added as kwargs to
  `get_llm()` rather than behind a Protocol method.

---

## Follow-ups (not part of this decision)

- Add the Anthropic branch to `get_llm()` (`ChatAnthropic`).
- Remove `backend/llm/client.py`, `_openai.py`, `_anthropic.py`, `_local.py` once the RAG
  pipeline is implemented and nothing references them.
- Write a backend-RAG ADR covering retrieval (`rag/retriever.py`) and graph traversal
  (`rag/graph_traversal.py`) design, building on ADR-0001's `VectorCypherRetriever`
  mandate.

---

## References

- `backend/api/dependencies.py` — canonical `get_llm()` implementation
- `backend/api/routes/chat.py` — the live consumer (`create_agent` + `VercelStream`)
- `backend/llm/client.py` — deprecated dispatcher (unused)
- ADR-0001 — graph database selection; mandates `neo4j-graphrag`
  `VectorCypherRetriever` for retrieval
