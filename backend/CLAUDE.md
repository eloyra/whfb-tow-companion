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

**LLM provider**: always resolved from `LLM_PROVIDER` env var via `llm/client.py`. Never import or instantiate a provider directly in routes or RAG code.

**Routes stay thin**: business logic lives in `rag/pipeline.py`, not in `api/routes/`. Route handlers call `pipeline.py` and return the result.

**Vector store**: Neo4j built-in vector index (HNSW). No separate ChromaDB or Pinecone.

**Streaming**: frontend uses Vercel AI SDK. Use `api/vercel_stream.py` to format SSE responses — do not invent a different streaming protocol.

**Graph access**: always go through the RAG pipeline (`rag/pipeline.py`) for retrieval. Graph traversal lives in `rag/graph_traversal.py`.

---

## Status

All files are stubs with `# TODO` docstrings. Implementations pending. The scrape and parse stages are complete upstream (see `pipeline/CLAUDE.md`).

RAG design not yet finalised. Check `docs/decisions/` for any ADRs added before starting work here.

---

Uses `LLM_*`, `NEO4J_*`, and `API_*` vars from root `.env` (full list in `../.env.example`).
