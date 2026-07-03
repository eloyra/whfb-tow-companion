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

**LLM provider**: resolved from `LLM_PROVIDER` env var via `api/dependencies.py::get_llm()`, which returns a LangChain `BaseChatModel` (required by `create_agent`). See ADR-0007. The older `llm/client.py` Protocol + `_openai.py`/`_anthropic.py`/`_local.py` abstraction is **deprecated** and unused; do not add new code to it. Providers supported today: Ollama (default), OpenAI, Anthropic.

**Routes stay thin** (target convention): business logic lives in `rag/pipeline.py`; `api/routes/chat.py` now injects `get_rag_pipeline()` and lets the pipeline build the tool-calling agent.

**Vector store**: Neo4j built-in vector index (HNSW). No separate ChromaDB or Pinecone.

**Streaming**: frontend uses Vercel AI SDK. Use `api/vercel_stream.py` to format SSE responses — do not invent a different streaming protocol. `vercel_stream.py` normalizes retrieved source nodes to the frontend contract (`id`, `label`, `text`, `source_url`).

**Graph access**: always go through the RAG pipeline (`rag/pipeline.py`) for retrieval. Graph traversal lives in `rag/graph_traversal.py`.

---

## Status

Not all files are stubs. Per-file state:

| File | State |
|---|---|
| `api/main.py` | Implemented — FastAPI app, CORS, `/health`, mounts `chat` + `graph` routers |
| `api/routes/chat.py` | Implemented — `POST /chat/` builds a LangGraph agent (`create_agent`) and streams via `VercelStream` |
| `api/routes/graph.py` | Stub — `/graph/nodes` and `/graph/subgraph/{node_id}` raise `NotImplementedError` |
| `api/vercel_stream.py` | Implemented — Vercel AI SDK v6 UI Message Stream SSE adapter |
| `api/dependencies.py` | Implemented — `get_llm()` (Ollama/OpenAI/Anthropic via LangChain), `get_driver()`, `get_embedder()`, `get_rag_pipeline()` |
| `llm/client.py` | Dispatcher implemented but **deprecated/unused** (ADR-0007); delegates to stubbed submodules |
| `llm/_openai.py`, `_anthropic.py`, `_local.py` | Stubs (`# TODO`) — deprecated, do not implement |
| `rag/tools.py` | Implemented — `build_tools()` factory wires the real `RAGPipeline` into a LangChain `@tool` |
| `rag/prompts/system_prompt.py` | Implemented — polished `SYSTEM_PROMPT` with mandatory tool use and citations |
| `rag/prompts/templates.py` | Stub (`# TODO`) |
| `rag/retriever.py` | Implemented — `GraphRAGRetriever`: multi-label vector search over Neo4j HNSW indexes |
| `rag/graph_traversal.py` | Implemented — `expand()` (bounded 1-hop neighbourhood) + `links_between()` (direct seed-to-seed edges) |
| `rag/pipeline.py` | Implemented — `RAGPipeline` orchestrates retrieve → traverse → format for the LLM |

Upstream scrape/parse/graph/embeddings stages are complete (see `pipeline/CLAUDE.md`). The baseline GraphRAG pipeline is implemented; a future ADR will formally capture the retrieval/traversal design if it moves beyond this baseline.

---

Uses `LLM_*`, `NEO4J_*`, and `API_*` vars from root `.env` (full list in `../.env.example`).
