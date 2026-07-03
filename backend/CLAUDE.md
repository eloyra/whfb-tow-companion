# CLAUDE.md — backend/

Scoped context for the FastAPI backend (REST API + RAG pipeline + LLM provider abstraction).
For project overview, stack, environment variables, and coding conventions, see [`../CLAUDE.md`](../CLAUDE.md).

---

## Layout

```
backend/
  api/
    main.py           ← FastAPI app, mounts routes
    routes/           ← thin route handlers (chat.py, graph.py)
    vercel_stream.py  ← Vercel AI SDK streaming format helper
    dependencies.py   ← FastAPI deps (DB session, etc.)
  rag/
    pipeline.py       ← entry point for all retrieval; routes call this
    retriever.py      ← vector search against Neo4j
    graph_traversal.py← multi-hop graph traversal
    prompts/          ← system prompt, message templates
  llm/
    client.py         ← provider abstraction (returns unified interface)
    _openai.py
    _anthropic.py
    _local.py         ← Ollama / local inference
```

---

## Key rules

**LLM provider**: resolved from `LLM_PROVIDER` env var via `api/dependencies.py::get_llm()`, which returns a LangChain `BaseChatModel` (required by `create_agent`). See ADR-0007. The older `llm/client.py` Protocol + `_openai.py`/`_anthropic.py`/`_local.py` abstraction is **deprecated** and unused; do not add new code to it. Providers supported today: Ollama (default), OpenAI. Anthropic is a known gap (no branch in `get_llm()` yet).

**Routes stay thin** (target convention): business logic should live in `rag/pipeline.py`, not in `api/routes/`. This is **not yet enforced** — `rag/pipeline.py` is a `# TODO` stub, so `routes/chat.py` currently builds its LangGraph agent inline. When the RAG pipeline is implemented, move the agent construction into `pipeline.py` and have `chat.py` call it.

**Vector store**: Neo4j built-in vector index (HNSW). No separate ChromaDB or Pinecone.

**Streaming**: frontend uses Vercel AI SDK. Use `api/vercel_stream.py` to format SSE responses — do not invent a different streaming protocol.

**Graph access**: always go through the RAG pipeline (`rag/pipeline.py`) for retrieval. Graph traversal lives in `rag/graph_traversal.py`. (Both currently stubs.)

---

## Status

Not all files are stubs. Per-file state:

| File | State |
|---|---|
| `api/main.py` | Implemented — FastAPI app, CORS, `/health`, mounts `chat` + `graph` routers |
| `api/routes/chat.py` | Implemented — `POST /chat/` builds a LangGraph agent (`create_agent`) and streams via `VercelStream` |
| `api/routes/graph.py` | Stub — `/graph/nodes` and `/graph/subgraph/{node_id}` raise `NotImplementedError` |
| `api/vercel_stream.py` | Implemented — Vercel AI SDK v6 UI Message Stream SSE adapter |
| `api/dependencies.py` | Implemented — `get_llm()` (Ollama/OpenAI via LangChain); `get_retriever()` not yet added |
| `llm/client.py` | Dispatcher implemented but **deprecated/unused** (ADR-0007); delegates to stubbed submodules |
| `llm/_openai.py`, `_anthropic.py`, `_local.py` | Stubs (`# TODO`) — deprecated, do not implement |
| `rag/tools.py` | Partial — `query_warhammer_archive` `@tool` returns hardcoded mock nodes; flagged for replacement with real GraphRAG calls |
| `rag/prompts/system_prompt.py` | Implemented — `SYSTEM_PROMPT` constant |
| `rag/prompts/templates.py` | Stub (`# TODO`) |
| `rag/pipeline.py`, `retriever.py`, `graph_traversal.py` | Stubs (`# TODO`) — the GraphRAG core is not yet implemented (next task) |

Upstream scrape/parse/graph/embeddings stages are complete (see `pipeline/CLAUDE.md`). RAG design is not yet finalised; ADR-0007 locks the LLM-provider path. A future ADR will cover RAG retrieval/traversal design.

---

Uses `LLM_*`, `NEO4J_*`, and `API_*` vars from root `.env` (full list in `../.env.example`).
