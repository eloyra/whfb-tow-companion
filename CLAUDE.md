# CLAUDE.md — Project Context for Claude Code

This file gives you all the context you need to work on this project effectively. Read it fully before making any changes.

---

## What this project is

A **conversational assistant for Warhammer: The Old World** (a tabletop miniature wargame by Games Workshop). It is built as a TFM (Master's thesis) for the UNIR Máster Universitario en Inteligencia Artificial.

The system answers two types of queries:
1. **Rules questions** — e.g. "What happens when a unit with Regeneration is hit by Flaming Attacks?"
2. **Army building assistance** — e.g. "Build me a 2000pt Vampire Counts list focused on magic"

The core architecture is **GraphRAG**: semantic vector search over a knowledge graph, combined with graph traversal for multi-hop reasoning over interrelated rules.

---

## Architecture overview

```
tow.whfb.app (wiki)
      │
      ▼
pipeline/           ← data pipeline (run once, or on wiki updates)
  scraper/          ← crawl wiki HTML
  parsers/          ← extract structured data from HTML
  graph/            ← build Neo4j knowledge graph
  embeddings/       ← generate vectors, write to Neo4j node properties
  i18n/             ← add translations to graph nodes
      │
      ▼
data/
  parsed/           ← intermediate JSON (nodes + edges)
  graph/            ← Cypher DDL, import scripts, index definitions
      │
      ▼
backend/            ← FastAPI serving the GraphRAG pipeline
  api/              ← REST endpoints (/chat, /graph)
  rag/              ← retrieval + graph traversal + LLM orchestration
  llm/              ← provider abstraction (OpenAI / Anthropic / local)
      │
      ▼
frontend/           ← Streamlit chat interface + graph visualisation
```

---

## Data source

**URL:** https://tow.whfb.app  
**Type:** Static HTML, no JavaScript rendering needed. BeautifulSoup is sufficient.  
**License:** Community rules index, educational use.  
**Structure:** Every page is a separate URL with a predictable slug pattern:

| URL pattern | Content |
|---|---|
| `/army/{slug}` | Army index page listing all units |
| `/unit/{slug}` | Unit profile with stats, equipment, special rules |
| `/special-rules/{slug}` | Special rule with full text |
| `/{section}/{slug}` | Core rulebook mechanics |
| `/the-lores-of-magic/{slug}` | Magic lore and spells |
| `/magic-items/{slug}` | Magic items |
| `/weapons-of-war/{slug}` | Weapons and armour |
| `/troop-types-in-detail/{slug}` | Troop type definitions |
| `/faq` | Official FAQ |
| `/errata` | Official errata |

The 19 armies are: Beastmen Brayherds, Chaos Dwarfs, Daemons of Chaos, Dark Elves, Dwarfen Mountain Holds, Empire of Man, Grand Cathay, High Elf Realms, Kingdom of Bretonnia, Lizardmen, Ogre Kingdoms, Orc & Goblin Tribes, Realms of Men, Regiments of Renown, Skaven, Tomb Kings of Khemri, Vampire Counts, Warriors of Chaos, Wood Elf Realms.

---

## Knowledge graph schema

Full schema in `docs/schema/knowledge_graph_schema.md` — read it before touching any pipeline or graph code.

Node types: `Army`, `Unit`, `SpecialRule`, `CoreRule`, `Document`, `TroopType`, `Weapon`, `Spell`, `MagicItem`, `FAQ`, `Errata`.  
Edge types — structural: `BELONGS_TO`, `HAS_TYPE`, `HAS_RULE`, `HAS_OPTIONAL_RULE`, `HAS_WEAPON`, `HAS_OPTIONAL_WEAPON`, `CAN_MOUNT`, `CAN_TAKE_ITEM`, `USES_LORE`, `PART_OF_SECTION`; semantic: `REFERENCES`; clarification: `CLARIFIES`, `AMENDS`.

Key design decisions (parse contract, `CHARACTERISTIC_MAP`, i18n conventions) live in `pipeline/CLAUDE.md`.

---

## Tech stack

| Component | Technology | Notes |
|---|---|---|
| Scraping | `requests` + `beautifulsoup4` | Static HTML, no JS rendering needed |
| Graph | Neo4j Community Edition 5.x | Docker; Cypher DDL in `pipeline/graph/`; vector index built-in (HNSW) |
| Embeddings | `sentence-transformers` | `paraphrase-multilingual-mpnet-base-v2` |
| Vector store | Neo4j vector index | Colocated with graph — no separate ChromaDB needed |
| LLM | Configurable via `LLM_PROVIDER` env var | OpenAI / Anthropic / local (Ollama) |
| Orchestration | `langchain` / `langgraph` | TBD during RAG phase |
| Backend API | `fastapi` + `uvicorn` | |
| Frontend | TanStack Start + React 19 | See `frontend/CLAUDE.md`; not Streamlit — `make ui` was removed |
| Package manager | `uv` | Preferred over pip/poetry |
| Linter | `ruff` | |
| Tests | `pytest` | |

---

## Environment variables

All config via `.env` (copy from `.env.example`):

```
LLM_PROVIDER        openai | anthropic | local
LLM_MODEL           model name (e.g. gpt-4o)
OPENAI_API_KEY
ANTHROPIC_API_KEY
LOCAL_LLM_BASE_URL  e.g. http://localhost:11434 for Ollama
RAG_MODE            vector | graph (default) | hybrid — retrieval-mode ablation, see ADR-0008
EMBEDDING_MODEL     paraphrase-multilingual-mpnet-base-v2
NEO4J_URI           bolt://localhost:7687
NEO4J_USER          neo4j
NEO4J_PASSWORD      changeme
SCRAPE_DELAY_SECONDS  1.0 (be polite to the wiki)
SCRAPE_BASE_URL     https://tow.whfb.app
API_HOST            0.0.0.0
API_PORT            8000
```

---

## Common commands

```bash
make install        # install all dependencies
make scrape         # crawl wiki → data/raw/
make parse          # parse HTML → data/parsed/
make build-graph    # build graph → data/graph/
make embed          # generate embeddings → data/embeddings/
make translate      # add translations to graph nodes
make pipeline       # run all stages end to end
make serve           # start API on :8000
make test            # run all tests
make lint           # run ruff
make evaluate        # retrieval-only evaluation against the golden set
make evaluate-full   # full agent + LLM-judge evaluation
make evaluate-compare  # compare vector/graph/hybrid retrieval modes (ADR-0008)
```

---

## Current project status

- [x] Directory and file structure
- [x] Knowledge graph schema (`docs/schema/knowledge_graph_schema.md`)
- [x] `pyproject.toml` with all dependencies
- [x] `pipeline/constants.py` with `CHARACTERISTIC_MAP`, `NodeType`, `EdgeType`
- [x] `pipeline/run_pipeline.py` entry point
- [x] `pipeline/scraper/crawler.py` — dual-seed BFS crawler (ADR-0002)
- [x] `pipeline/scraper/parsers/*.py` — 13 parsers + coordinator (ADR-0003, ADR-0006)
- [x] `pipeline/graph/` — builder, client, DDL, loader, seeds, validator (ADR-0001, ADR-0004, ADR-0005); `load_report.json` produced
- [x] `pipeline/embeddings/` — generator, per-label text builders, HNSW vector_store (ADR-0005)
- [x] `backend/api/main.py` — FastAPI app wired; `/chat` route implemented (LangGraph agent + Vercel SSE); `/graph` routes (`/graph/nodes`, `/graph/subgraph/{id}`) implemented (ADR-0009)
- [x] `backend/llm/` — `client.py` dispatcher exists but provider submodules are stubs; **deprecated** in favour of `api/dependencies.py::get_llm()` (ADR-0007)
- [x] `backend/rag/` — `retriever.py`, `graph_traversal.py`, `pipeline.py`, `tools.py` (semantic search + deterministic army-roster tool), `prompts/templates.py` (provider-aware system-prompt composition), `prompts/system_prompt.py` (compat shim) implemented
- [x] `pipeline/i18n/` — `translator.py` implements `Translator` (local Ollama model, flat `name_es`/`text_es`); ~62% of SpecialRule translated, other labels pending
- [x] `tests/evaluation/` — `evaluate.py` implemented (retrieval-only + full agent/LLM-judge modes, `--compare` retrieval-mode ablation); 100-query golden set
- [x] Frontend graph visualisation — `widgets/graph-viewer/` + `/graph` route implemented (see `frontend/CLAUDE.md`)

---

## Coding conventions

- Python 3.11+, type hints everywhere.
- Line length 100 (configured in `pyproject.toml`).
- All imports sorted by ruff (`make lint`).
- Every module has a docstring explaining its purpose.
- Stub files contain `# TODO` and a docstring — never pass silently.
- No hardcoded URLs, delays, or model names — always read from constants or env.
- Scraper must respect `SCRAPE_DELAY_SECONDS` between requests.
- Graph node IDs are always the URL slug (e.g. `"blood-knights"`, `"fear"`).
- `null` in JSON / `None` in Python for missing stat values (never `"-"` or `0`).

---

## Documentation and design decisions

The `docs/` folder is the authoritative source for design context beyond what is in CLAUDE.md:

- `docs/schema/` — knowledge graph schema (read before touching any pipeline or graph code)
- `docs/decisions/` — Architecture Decision Records (ADRs); **read the relevant ADR before working on any component it covers.** Each ADR explains what was decided, why, and what alternatives were rejected — this context prevents re-litigating closed decisions.
- `docs/diagrams/` — architecture and flow diagrams

When you are about to implement or modify a component, check `docs/decisions/` first for an ADR that covers it. If one exists, its constraints and rationale are binding unless the user explicitly overrides them.

---

## Language

All code, comments, docstrings, commit messages, documentation, and any other text produced in this repository must be in English. This includes inline comments, variable names that contain words, log messages, error messages, test descriptions, and markdown files. The only exception is content inside i18n fields within data files, where Spanish translations are intentionally stored alongside English. If you are unsure whether something counts as project text, default to English.

---

## Progressive disclosure

Each top-level subdirectory has a scoped `CLAUDE.md` (and an `AGENTS.md` symlink to it) that covers only what is relevant to that subtree. When working inside a subdirectory, load its `CLAUDE.md` instead of (or in addition to) this file.

| Directory | Scoped context |
|---|---|
| `pipeline/` | Parsers, graph builder, constants, ADR pointers, parse contract |
| `backend/` | FastAPI layout, RAG pipeline, LLM provider rules, streaming |
| `frontend/` | TanStack Start, FSD architecture, Paraglide i18n, pnpm, Biome |
| `docs/` | ADR authority, schema authority, what is binding vs. reference |
| `tests/` | Unit/integration/evaluation layout, golden query set |