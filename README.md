# Warhammer: The Old World — Conversational RAG Assistant

A conversational assistant for Warhammer: The Old World built with GraphRAG (Graph-enhanced Retrieval-Augmented Generation). The system combines semantic vector search with knowledge graph traversal to answer complex rule queries and assist with army list building. Built as a TFM (Master's thesis) for the UNIR Máster Universitario en Inteligencia Artificial.

**Data source:** [tow.whfb.app](https://tow.whfb.app) — community rules index (educational use)

## Architecture

- **Knowledge graph:** Neo4j Community Edition 5.x — 17 node types (Army, Unit, SpecialRule, CoreRule, Spell, MagicItem, Weapon, FAQ, Errata, etc.), 27 edge types (explicit hyperlinks/membership + derived/semantic relations like `CAN_TAKE_ITEM`, `REFERENCES`, `CLARIFIES`, `AMENDS`)
- **Embeddings:** `paraphrase-multilingual-mpnet-base-v2` (multilingual, single vector space), 13 per-label HNSW vector indexes
- **Vector store:** Neo4j vector index (colocated with graph — no separate ChromaDB/Pinecone)
- **Retrieval modes:** `RAG_MODE` env var selects `vector` (naive RAG baseline), `graph` (GraphRAG: vector + lexical boost + 1-hop traversal), or `hybrid` (+ BM25/vector RRF fusion) — see ADR-0008
- **LLM:** Configurable via `LLM_PROVIDER` — OpenAI / Anthropic / local (Ollama); citation via Anthropic native `search_result` blocks when using Claude
- **Orchestration:** LangChain / LangGraph
- **Backend:** FastAPI, streams responses over SSE (Vercel AI SDK format)
- **Frontend:** TanStack Start + React 19 (Feature-Sliced Design) — chat interface and an interactive knowledge-graph viewer
- **i18n:** Spanish translations (`name_es`/`text_es`) via a local Ollama model

## Quick start

```bash
cp .env.example .env        # fill in your API keys
make install                # install dependencies
make pipeline               # scrape → parse → graph → embed → translate (takes a while)
make serve                  # start API on :8000

cd frontend && pnpm install && pnpm dev   # start frontend on :3000 (chat + /graph viewer)
```

## Project structure

See `docs/schema/knowledge_graph_schema.md` for the full knowledge graph schema.
See `docs/decisions/` for architecture decision records (ADR-0001 through ADR-0009).
See `pipeline/CLAUDE.md`, `backend/CLAUDE.md`, `frontend/CLAUDE.md` for scoped context per subtree.

## Development

```bash
make test               # run all tests
make lint                # run linter

make evaluate            # retrieval-only evaluation against the golden set
make evaluate-full       # full agent + LLM-judge evaluation
make evaluate-compare    # compare vector/graph/hybrid retrieval modes
make evaluate-compare-full  # full agent + LLM-judge comparison across all 3 modes
```
