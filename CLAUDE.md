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
  graph/            ← build NetworkX knowledge graph
  embeddings/       ← generate vectors, populate ChromaDB
  i18n/             ← add translations to graph nodes
      │
      ▼
data/
  parsed/           ← intermediate JSON (nodes + edges)
  graph/            ← serialized NetworkX graph (.graphml)
  embeddings/       ← ChromaDB vector store
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

Full schema is in `docs/schema/knowledge_graph_schema.md`. Summary:

### Node types
- `Army` — faction (19 total)
- `Unit` — unit, character, or mount with stat profile
- `Rule` — special rule (universal / army-specific / unique)
- `CoreRule` — rulebook mechanics (movement, shooting, combat phases, etc.)
- `TroopType` — troop type definitions (Heavy Cavalry, Regular Infantry, etc.)
- `Weapon` — weapons, armour, equipment
- `Spell` — individual spells from magic lores
- `MagicItem` — magic items and army-specific powers (e.g. Vampiric Powers)
- `FAQ` — official FAQ entries
- `Errata` — official errata corrections

### Edge types (directed)
Structural: `BELONGS_TO`, `HAS_TYPE`, `HAS_RULE`, `HAS_OPTIONAL_RULE`, `HAS_WEAPON`, `HAS_OPTIONAL_WEAPON`, `CAN_MOUNT`, `CAN_TAKE_ITEM`, `USES_LORE`, `PART_OF_SECTION`  
Semantic (from hyperlinks in text): `REFERENCES`  
Clarification: `CLARIFIES`, `AMENDS`

### Key design decisions
- **English is the canonical language.** All data scraped from wiki is English.
- **Multilingual via `i18n` field.** Every node has `"i18n": {"en": {...}, "es": {...}}` for translatable fields (`name`, `text`). Structural fields (`id`, `url`, `source_citation`, stats) are invariant.
- **Embeddings use a multilingual model** (`paraphrase-multilingual-mpnet-base-v2`) so a Spanish query finds English nodes without translation.
- **`CHARACTERISTIC_MAP` in `pipeline/constants.py`** maps stat abbreviations (M, WS, BS...) to CoreRule node IDs. This avoids adding 1800 redundant edges (200 units × 9 stats) to the graph.
- **`troop_type_id` stored as attribute AND as edge** (`HAS_TYPE`) for convenience when serializing nodes to the vector store without graph traversal.
- **Stats use `null` for `-`** (characteristic not applicable to a subprofile).
- **`source_citation` is always an object:** `{"book": "Vampire Counts", "page": 13}`.

---

## Tech stack

| Component | Technology | Notes |
|---|---|---|
| Scraping | `requests` + `beautifulsoup4` | Static HTML, no JS rendering needed |
| Graph | `networkx` (DiGraph) | May migrate to Neo4j if scale requires |
| Embeddings | `sentence-transformers` | `paraphrase-multilingual-mpnet-base-v2` |
| Vector store | `chromadb` | Local by default |
| LLM | Configurable via `LLM_PROVIDER` env var | OpenAI / Anthropic / local (Ollama) |
| Orchestration | `langchain` / `langgraph` | TBD during RAG phase |
| Backend API | `fastapi` + `uvicorn` | |
| Frontend | `streamlit` | Chat UI + graph visualisation |
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
EMBEDDING_MODEL     paraphrase-multilingual-mpnet-base-v2
VECTOR_STORE_PATH   data/embeddings/chroma
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
make serve          # start API on :8000
make ui             # start Streamlit on :8501
make test           # run all tests
make lint           # run ruff
```

---

## Current project status

The project is in **initial setup phase**. The following have been defined but not yet implemented:

- [x] Directory and file structure
- [x] Knowledge graph schema (`docs/schema/knowledge_graph_schema.md`)
- [x] `pyproject.toml` with all dependencies
- [x] `pipeline/constants.py` with `CHARACTERISTIC_MAP`, `NodeType`, `EdgeType`
- [x] `pipeline/run_pipeline.py` entry point (stubs only)
- [x] `backend/api/main.py` (wired up, routes not implemented)
- [x] `backend/llm/client.py` (abstraction, implementations pending)
- [x] Sample data in `data/samples/vampire-counts-sample.json`
- [ ] `pipeline/scraper/crawler.py` — **next task**
- [ ] `pipeline/scraper/parsers/*.py` — after crawler
- [ ] `pipeline/graph/builder.py`
- [ ] `pipeline/embeddings/`
- [ ] `backend/rag/`
- [ ] `frontend/`

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

## Important files to read before working on a component

| Working on | Read first |
|---|---|
| Scraper / parsers | `docs/schema/knowledge_graph_schema.md`, `pipeline/constants.py` |
| Graph builder | `docs/schema/knowledge_graph_schema.md`, `pipeline/constants.py` |
| RAG pipeline | `backend/rag/pipeline.py`, `backend/llm/client.py` |
| API routes | `backend/api/main.py`, `backend/api/routes/chat.py` |
| Translations | `pipeline/i18n/translator.py`, `pipeline/constants.py` (SUPPORTED_LANGUAGES) |
| Tests | `tests/evaluation/test_queries.json` for expected behaviour |

---

## Language

All code, comments, docstrings, commit messages, documentation, and any other text produced in this repository must be in English. This includes inline comments, variable names that contain words, log messages, error messages, test descriptions, and markdown files. The only exception is content inside i18n fields within data files, where Spanish translations are intentionally stored alongside English. If you are unsure whether something counts as project text, default to English.