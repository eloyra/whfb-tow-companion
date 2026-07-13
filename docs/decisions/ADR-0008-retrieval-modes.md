# ADR-0008 — Retrieval-Mode Ablation (vector / graph / hybrid)

| Field       | Value                          |
|-------------|--------------------------------|
| **Status**  | Accepted                       |
| **Date**    | 2026-07-13                     |
| **Deciders**| Project author                 |
| **Tags**    | backend, rag, evaluation, retrieval |

---

## Context

The system shipped a single retrieval strategy: per-label vector ANN search,
an in-memory lexical exact-name-match boost, and 1-hop graph traversal (the
"GraphRAG" baseline — see ADR-0001). For the thesis evaluation, a bare vector
result is not sufficient evidence that graph traversal or hybrid retrieval
carry their weight; the golden 100-query set (`tests/evaluation/test_queries.json`)
needs to be run under multiple retrieval strategies so the recall/judge
numbers can be compared directly.

Three modes are needed:

1. **Naive / simple RAG** — pure vector top-k, no traversal. The textbook
   baseline every RAG-vs-GraphRAG paper compares against.
2. **GraphRAG** (the existing baseline) — vector search + graph traversal
   (1-hop neighborhood + direct seed-to-seed links).
3. **Hybrid** — GraphRAG's traversal, but vector search fused with a
   standard BM25/full-text ranking via Reciprocal Rank Fusion (RRF), instead
   of the handcrafted lexical name-match boost.

The three must be selectable by a single env var so the full evaluation
harness can re-run per mode without code changes, per query from the eval
harness's `--compare` flag.

---

## Decision

### Two independent knobs, three named modes

Graph traversal is the *defining trait* of the `graph` mode. The lexical
name-match fallback is a secondary, hand-tuned add-on that could be dropped
entirely without changing what "GraphRAG" means here — so it is its own
independent knob, not folded into the mode's identity or into `strategy`.

- **`GraphRAGRetriever.strategy`** (`"vector"` | `"hybrid"`, default
  `"vector"`) — controls only whether the full-text BM25 ranking is fused in
  via RRF.
- **`GraphRAGRetriever.lexical_fallback`** (`bool`, default `False`) — the
  existing exact-name-match boost (`backend/rag/retriever.py::_lexical_matches`),
  orthogonal to `strategy`.
- **`RAGPipeline.expand`** (`bool`, default `True`) — when `False`, skips
  `traversal.expand()` / `links_between()` entirely and formats context from
  seed nodes only (`RAGPipeline._format_seeds_only`).

`RAG_MODE` env var (default `graph`) maps to `(strategy, lexical_fallback, expand)`
via `backend/api/dependencies.py::resolve_rag_mode()`:

| `RAG_MODE` | `strategy` | `lexical_fallback` | `expand` | = |
|---|---|---|---|---|
| `vector` | `vector` | `False` | `False` | naive/simple RAG baseline |
| `graph` (default) | `vector` | `True` | `True` | GraphRAG baseline (current behaviour, unchanged) |
| `hybrid` | `hybrid` | `False` | `True` | GraphRAG + BM25/vector RRF fusion |

`resolve_rag_mode()` is the single source of truth for this mapping; both
`get_rag_pipeline()` (the live `/chat` path) and the evaluation harness
(`tests/evaluation/runner.py::build_retriever`) call it, so the mode-to-knob
mapping cannot drift between production and evaluation.

### Hybrid retrieval: one full-text index + RRF fusion

`pipeline/graph/ddl.py` creates **one** multi-label full-text index,
`archive_fulltext_idx`, over `(n.name, n.text)` across every
`EMBEDDABLE_LABELS` label:

```cypher
CREATE FULLTEXT INDEX archive_fulltext_idx IF NOT EXISTS
FOR (n:SpecialRule|CoreRule|Document|TroopType|Spell|MagicItem|Lore|FAQ|Errata|Weapon|Unit|Army|Terrain)
ON EACH [n.name, n.text]
```

Unlike vector indexes (which require at least one populated node before
Neo4j accepts the type hint — see `pipeline/embeddings/vector_store.py`),
full-text indexes have no such requirement, so this lives in DDL alongside
the constraints/btree indexes rather than in the embeddings stage.

`backend/rag/retriever.py::_query_fulltext` runs
`db.index.fulltext.queryNodes` against this index and returns an
already-globally-ranked BM25 list (`_lucene_escape` backslash-escapes Lucene
special characters — `?`, `:`, parentheses, etc. — since raw golden-set
queries like *"What is the Stubborn rule?"* would otherwise throw a Lucene
parser error).

`GraphRAGRetriever._fuse_rrf(vector_ranked, fulltext_ranked, k_const=RRF_K)`
combines the two ranked lists in Python:

```
score(node) = Σ 1 / (RRF_K + rank_in_list)
```

summed over every list the node appears in (1-based rank). `RRF_K = 60` is
the standard constant from the original RRF paper (Cormack et al., 2009) —
not query-tuned. The fused score **replaces** each node's original
cosine/BM25 score; the two are on incomparable scales, so only the
rank-based fused score is meaningful once both lists are merged.

### Why fusion is Python, not pure Cypher

Vector indexes in this system are **per-label-per-property** (13 separate
HNSW indexes, one per `EMBEDDABLE_LABELS` entry — ADR-0001, ADR-0005), each
queried independently and merged in Python by cosine score. No single
Cypher query spans all 13 vector indexes, so a global rank fusion cannot
live entirely inside one query.

Full-text search *can* be — and is — a single multi-label index, so that
side of the fusion is pure Cypher: one `db.index.fulltext.queryNodes` call
returns one globally-ranked BM25 list, no per-label merge step needed.
Cypher therefore owns both retrieval calls (per-label vector ANN × 13, plus
one full-text query); Python owns only the RRF rank-merge of the two
already-ranked lists — a small, pure, unit-testable function
(`_fuse_rrf`) with no Neo4j dependency.

### Evaluation harness

`tests/evaluation/evaluate.py` gains:

- `--mode {vector,graph,hybrid}` — single-mode override (default: `RAG_MODE`
  env var, or `graph`).
- `--compare` — runs all three modes over the same golden set and emits a
  `ComparisonReport` (JSON + Markdown) with per-mode mean recall@k,
  per-category recall (`tests/evaluation/scoring.py::per_category_recall`),
  and below-threshold counts side by side. Retrieval-only by default (no LLM
  cost); combine with `--full` for the agent + judge comparison.

`make evaluate-compare` runs the default (retrieval-only) comparison.

---

## Consequences

### Positive

- One env var (`RAG_MODE`) switches the entire retrieval behaviour for both
  the live `/chat` path and the evaluation harness, with no risk of the two
  drifting apart (single `resolve_rag_mode()` source of truth).
- The ablation cleanly isolates two variables: graph traversal (`expand`)
  and hybrid rank fusion (`strategy`), rather than conflating them.
- `_fuse_rrf` and `_lucene_escape` are pure functions, unit-tested without
  Neo4j (`tests/unit/test_retriever.py`).
- The lexical name-match boost remains fully removable (set
  `lexical_fallback=False` in the `graph` row of `_RAG_MODE_CONFIG`) without
  touching graph-traversal behaviour — it was never load-bearing for what
  "GraphRAG" means in this system.

### Negative / accepted trade-offs

- Hybrid mode issues 14 Cypher calls per query (13 vector + 1 full-text)
  instead of 13 — acceptable at thesis scale (a few thousand nodes).
- `RRF_K=60` is a literature default, not tuned against this golden set;
  tuning it is a possible follow-up once comparison numbers are in.
- The full-text index must be (re)created via `apply_constraints_and_indexes`
  (part of `make build-graph`) before `hybrid` mode can be evaluated; it is
  not created automatically by `make embed`.

---

## Follow-ups (not part of this decision)

- Run `make evaluate-compare` (and `--full --compare`) once the full-text
  index is live, and record the measured recall/judge numbers in the
  project roadmap.
- Consider tuning `RRF_K` against the golden set's measured recall.

---

## References

- `backend/rag/retriever.py` — `GraphRAGRetriever` (`strategy`,
  `lexical_fallback`, `_fuse_rrf`, `_query_fulltext`, `_lucene_escape`)
- `backend/rag/pipeline.py` — `RAGPipeline` (`expand`, `_format_seeds_only`)
- `backend/api/dependencies.py` — `resolve_rag_mode`, `get_rag_pipeline`
- `pipeline/graph/ddl.py` — `archive_fulltext_idx`
- `tests/evaluation/evaluate.py` — `--mode`, `--compare`
- ADR-0001 — graph database selection; per-label vector index design
- ADR-0005 — graph storage conventions (index naming)
- Cormack, G. V., Clarke, C. L. A., & Buettcher, S. (2009). *Reciprocal Rank
  Fusion outperforms Condorcet and individual rank learning methods.*
  SIGIR 2009.
