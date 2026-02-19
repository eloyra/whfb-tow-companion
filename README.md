# Warhammer: The Old World — Conversational RAG Assistant

A conversational assistant for Warhammer: The Old World built with GraphRAG (Graph-enhanced Retrieval-Augmented Generation). The system combines semantic vector search with knowledge graph traversal to answer complex rule queries and assist with army list building.

**Data source:** [tow.whfb.app](https://tow.whfb.app) — community rules index (educational use)

## Architecture

- **Knowledge graph:** NetworkX — nodes = rules/units/abilities, edges = explicit (hyperlinks) and implicit (semantic references)
- **Embeddings:** `paraphrase-multilingual-mpnet-base-v2` (multilingual, single vector space)
- **Vector store:** ChromaDB
- **LLM:** Configurable — OpenAI / Anthropic / local (Ollama)
- **Orchestration:** LangChain / LangGraph
- **Backend:** FastAPI
- **Frontend:** Streamlit

## Quick start

```bash
cp .env.example .env        # fill in your API keys
make install                # install dependencies
make pipeline               # scrape → parse → graph → embed (takes a while)
make serve                  # start API on :8000
make ui                     # start UI on :8501
```

## Project structure

See `docs/schema/knowledge_graph_schema.md` for the full knowledge graph schema.
See `docs/decisions/` for architecture decision records.

## Development

```bash
make test     # run tests
make lint     # run linter
```
