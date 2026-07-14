# Baseline GraphRAG Showcase — Runbook

This runbook explains how to run the end-to-end showcase for the Warhammer: The Old World conversational assistant. It covers data preparation, starting the backend and frontend, and a short set of manual smoke queries.

For the underlying implementation plan, see [`docs/plans/baseline-showcase-graphrag.md`](plans/baseline-showcase-graphrag.md).

---

## What is being showcased

1. **Semantic retrieval** — the user's question is embedded and matched against all embeddable node labels in Neo4j (HNSW vector indexes).
2. **Graph traversal** — the top seed nodes are expanded with a bounded 1-hop neighbourhood and direct seed-to-seed edges.
3. **Tool-calling agent** — a LangGraph agent decides when to call the archive tool, then answers with inline citations.
4. **Source chips in the UI** — retrieved nodes are streamed back as `data-sources` SSE events and rendered as clickable chips. Anthropic models use native `search_result` citations; other providers fall back to inline `[slug]` citations.
5. **Hover previews** — source chips show an iframe tooltip of the linked wiki page on hover.

---

## Prerequisites

- Python 3.11+ and `uv` installed.
- Node.js 20+ and `pnpm` installed for the frontend.
- Docker (or a running Neo4j 5.x instance).
- A copy of `.env` at the repository root (see `.env.example`).

---

## 1. Prepare the knowledge graph

Skip this section if you already have a populated Neo4j database with embeddings and HNSW indexes.

```bash
# Start Neo4j (optional — use your own instance if preferred)
make neo4j-up

# Install dependencies
make install

# Run the full data pipeline (scrape → parse → graph → embed)
# This is slow and network-intensive; use existing data/ if available.
make pipeline
```

Verify the graph and indexes:

```bash
uv run python - <<'PY'
from backend.api.dependencies import get_driver
from pipeline.constants import EMBEDDABLE_LABELS
import re
d = get_driver()
with d.session() as s:
    for label in EMBEDDABLE_LABELS:
        idx = f"{re.sub(r'([A-Z])', r'_\\1', label).lower().lstrip('_')}_embedding_idx"
        result = s.run("SHOW INDEXES YIELD name WHERE name = $n RETURN count(*) AS n", n=idx)
        print(idx, result.single()["n"])
d.close()
PY
```

---

## 2. Configure the LLM

Edit `.env`:

```bash
# Option A: local Ollama (default, no API key needed)
LLM_PROVIDER=local
LLM_MODEL=llama3.1:8b
LOCAL_LLM_BASE_URL=http://localhost:11434

# Option B: OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...

# Option C: Anthropic
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-5
ANTHROPIC_API_KEY=sk-ant-...
LLM_MAX_TOKENS=8192              # total output budget (thinking + answer)
ANTHROPIC_THINKING_DISPLAY=summarized   # summarized | omitted
```

> **Thinking:** Claude Sonnet 5 uses adaptive thinking by default. The backend streams reasoning content as `reasoning` SSE events, which the frontend can render now or ignore.

> **Note:** Ollama tool-calling is model-dependent and can be flaky. For the most reliable showcase, use OpenAI or Anthropic.

---

## 3. Start the backend

```bash
make serve
```

The API will be available at `http://localhost:8000`. The first request will be slow because `get_rag_pipeline()` loads the SentenceTransformer embedding model into memory.

Quick health check:

```bash
curl http://localhost:8000/health
```

---

## 4. Start the frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Open the URL shown by the dev server (usually `http://localhost:3000`).

---

## 5. Manual smoke tests

Ask the following questions in the chat UI and verify the behaviour.

### 5.1 Rules question — single rule

> What does the Stubborn special rule do?

**Expected:**
- The assistant calls the archive tool.
- A source chip labelled **Stubborn** appears and links to `https://tow.whfb.app/special-rules/stubborn`.
- The answer explains that Stubborn units ignore Combat Result modifiers when testing Break.

### 5.2 Rules interaction — two rules

> Can a unit with Regeneration use it against Flaming Attacks?

**Expected:**
- Source chips include **Regeneration** and **Flaming Attacks**.
- The answer states that Flaming Attacks cancel Regeneration.

### 5.3 Army-building eligibility

> Can a Vampire Lord take The Flayed Hauberk?

**Expected:**
- Retrieval finds the Lord-level Vampire Counts character (`vampire-count`) and `the-flayed-hauberk` magic item.
- `links_between()` returns a direct `CAN_TAKE_ITEM` edge if the item can be taken, or no edge if it cannot. In the current dataset the direct edge is only present for Black Knights and Blood Knights, so the assistant should report that the archive does not confirm eligibility for the Vampire Count character itself.
- The answer is grounded in the retrieved context.

### 5.4 Unit stats

> What are the stats of Blood Knights?

**Expected:**
- A source chip labelled **Blood Knights** appears.
- The answer lists Movement, Weapon Skill, Ballistic Skill, Strength, Toughness, Wounds, Initiative, Attacks, and Leadership if present in the graph.

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Connection refused` to Neo4j | Neo4j not running or wrong `NEO4J_URI` | Start Neo4j or update `.env`. |
| First chat request hangs for 30s+ | Embedding model loading | Wait; subsequent requests are fast. Use a faster model or SSD if needed. |
| No source chips appear | LLM did not call the tool, or frontend `data-sources` wiring is incomplete | Check backend logs for tool calls; confirm frontend registers the `data-sources` data-part schema. |
| Sources appear but are not clickable | Backend emitted `url` instead of `source_url` | `vercel_stream.py` normalizes this; confirm the deployed backend includes the latest version. |
| Hover preview is blank | Source site blocks framing with `X-Frame-Options` | The live wiki currently allows framing; blank previews for external URLs are expected. |
| Nonsensical answers with Ollama | Model does not reliably use tools | Switch to OpenAI or Anthropic. |

---

## 7. What is intentionally out of scope

- **i18n translation pipeline** (`pipeline/i18n/`) is partially populated — ~62% of `SpecialRule` names translated, other labels pending. Resumable via `make translate` (translation-memory cache avoids re-translating).
- **Evaluation harness** (`tests/evaluation/`) is implemented with a 100-query golden set; real evaluation runs manually via `make evaluate` (retrieval-only) or `make evaluate-full` (agent + LLM-judge).

---

## 8. Validation checklist

- [x] Neo4j is running and HNSW indexes exist for all embeddable labels.
- [x] `make test-unit` passes (full `pytest` suite: 302 passed, including evaluation scoring tests).
- [x] `make lint` passes.
- [x] Backend imports cleanly: `uv run python -c "from backend.api.main import app"`.
- [x] `/health` responds.
- [x] At least one manual chat query returns source chips and a grounded answer.
