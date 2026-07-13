# ADR-0009 — Retriever and Traversal Architecture

| Field       | Value                          |
|-------------|--------------------------------|
| **Status**  | Accepted                       |
| **Date**    | 2026-07-13                     |
| **Deciders**| Project author                 |
| **Tags**    | backend, rag, retrieval, graph  |

---

## Context

ADR-0001 mandated `neo4j-graphrag`'s `VectorCypherRetriever` for retrieval: "embed(query)
→ vector ANN over `node.embedding` → Cypher traversal of connected subgraph → context for
LLM ... provided out of the box, with no custom orchestration code." ADR-0007 later
listed writing an ADR for the retrieval/traversal design actually built — as opposed to
the one mandated — as an open follow-up. It was never written. This ADR closes that gap.

What actually shipped is `backend/rag/retriever.py::GraphRAGRetriever` (per-label vector
ANN, optional hybrid BM25+RRF fusion per ADR-0008, optional lexical name-match fallback)
and `backend/rag/graph_traversal.py::GraphTraversal` (bounded, per-relation-type-capped
1-hop `expand()`; direct-edge `links_between()`). Neither uses `neo4j-graphrag`'s
retriever classes. Before writing this ADR as a rubber stamp of that divergence, the
package (already an installed dependency — `neo4j-graphrag>=1.0.0` in `pyproject.toml`,
resolved to v1.14.1, actively maintained) was inspected directly at the source level to
check whether it could, in fact, have done what this system needs. The answer is
partial: yes for one slice, no for the rest — see Alternatives below.

---

## Alternatives considered

### `VectorCypherRetriever`, one instance per label

`neo4j_graphrag.neo4j_queries.NODE_VECTOR_INDEX_QUERY` is
`CALL db.index.vector.queryNodes($vector_index_name, ...) YIELD node, score` — the exact
same primitive `GraphRAGRetriever._query_label` calls directly. `VectorCypherRetriever
(driver, index_name, retrieval_query, ...)` takes a single `index_name`; nothing would
have stopped instantiating 13 of them (one per `EMBEDDABLE_LABELS` entry) and merging
in Python, exactly as `GraphRAGRetriever.retrieve()` does today.

**Rejected**: this would have added a Pydantic-validated wrapper class and a
`result_formatter` hook around a call we already make directly, for no behavioral gain
— and, per the next two points, the hybrid-fusion and traversal layers needed custom
code regardless. Wrapping only the vector-only path in the package's class while
hand-rolling everything else would fragment the codebase across two abstractions for a
single retrieval mode, with no consistency benefit.

### `HybridRetriever` / `HybridCypherRetriever`

The package does ship hybrid (vector + full-text) retrievers. Two independent reasons
they don't fit:

1. **Single-index assumption.** Both classes take exactly one `vector_index_name` and
   one `fulltext_index_name` (`neo4j_graphrag/retrievers/hybrid.py`). The package has no
   built-in mechanism to query multiple per-label vector indexes and merge the results
   — confirmed against the official docs and developer blog posts as well as the
   source; no such helper exists. Adopting it for `strategy="hybrid"` would mean
   collapsing to one global vector index, abandoning the per-label HNSW design
   ADR-0001/ADR-0005 chose specifically for cheaper label-scoped ANN queries — a
   different architectural decision this ADR is not the place to reopen.
2. **Ranker choice.** `neo4j_graphrag.types.HybridSearchRanker` has exactly two members:
   `NAIVE` (per-node **max** of two independently min-max-normalized scores — a node
   present in both the vector and full-text result lists gets whichever single
   normalized score is higher, with no reward for appearing in both) and `LINEAR`
   (`alpha·vector_score + (1-alpha)·fulltext_score`, requiring a tuned `alpha`).
   **Neither is Reciprocal Rank Fusion.** RRF (`GraphRAGRetriever._fuse_rrf`, ADR-0008)
   was chosen because it is rank-based — robust to the vector-cosine/BM25 score scales
   being incomparable — needs no tuned weight, and specifically rewards a node ranking
   well in *both* lists, which is the actual value proposition of running two retrieval
   signals in the first place. This is a substantive quality difference, not a
   preference for writing more code: `NAIVE`/`LINEAR` would not reproduce RRF's behavior
   even against a single global index.

**Rejected** on both grounds independently — either one alone would be sufficient.

### Collapse to a single global vector index to use the package's hybrid retriever as-is

**Rejected**: this would silently re-decide ADR-0001/ADR-0005's per-label indexing
choice as a side effect of writing a documentation-accuracy ADR. If per-label indexing
is ever revisited, it should get its own ADR with its own evaluation of the trade-off at
this project's actual scale (~7,800 nodes — small enough that the original "cheaper
label-scoped ANN" performance argument is weak, but the precision argument — avoiding
cross-label semantic bleed in a single global index — was not evaluated here and
shouldn't be assumed away).

---

## Decision

Retrieval and traversal are implemented as:

- **`backend/rag/retriever.py::GraphRAGRetriever`** — one HNSW vector index per label
  (13 of them, `pipeline.constants.EMBEDDABLE_LABELS`), queried via raw
  `db.index.vector.queryNodes` calls and merged in Python by cosine score.
  `strategy="hybrid"` additionally queries a single multi-label full-text index and
  fuses both ranked lists via Reciprocal Rank Fusion (ADR-0008 covers the RRF design in
  full; this ADR does not duplicate it). `lexical_fallback` is an independent, optional
  exact-name-match boost, orthogonal to `strategy`.
- **`backend/rag/graph_traversal.py::GraphTraversal`** — `expand()` returns bounded,
  per-relation-type-capped 1-hop neighbors (so no single high-fan-out relation type, e.g.
  `CAN_TAKE_ITEM`, starves every other relation type out of the result); `links_between()`
  returns direct edges among a set of seed nodes.
- **`RAG_MODE` ablation surface** (`vector`/`graph`/`hybrid`, ADR-0008,
  `backend/api/dependencies.py::resolve_rag_mode`) — the `strategy`/`lexical_fallback`/
  `expand` knobs above are exactly what make the retrieval-mode comparison in the
  evaluation harness possible. This is the practical payoff of the divergence: Chapter
  6's central empirical result (recall improves with reasoning-hop count under `graph`/
  `hybrid` vs. `vector`, with a paired significance test) required an experimentation
  surface no pre-built retriever class exposes — this holds regardless of the indexing
  and ranker points above, since `neo4j-graphrag`'s retriever classes have no traversal
  primitive and no notion of an ablatable "mode" at all.

## Consequences

### Positive
- Full control over the fusion algorithm (RRF, not `NAIVE`/`LINEAR`) and over traversal
  shaping (per-relation-type caps), both of which are load-bearing for retrieval quality
  and were verified empirically (ADR-0008's comparison run).
- The `RAG_MODE` ablation — the mechanism the thesis's evaluation chapter depends on for
  its central claim — exists at all because the retrieval layer is a plain Python
  object with orthogonal constructor flags, not a fixed pre-built class.

### Negative / accepted trade-offs
- This is genuinely more code to maintain than calling an actively-maintained official
  package (confirmed current: `neo4j-graphrag` v1.14.1) would have been, and it forgoes
  any future upstream improvements to that package's retrievers. This is an accepted,
  deliberate trade for RRF + per-label indexing + traversal/ablation control — not a
  case where no alternative existed; see Alternatives above for exactly what was
  available and why each was rejected.
- The per-label vector-index-merge pattern (`_query_label` × 13, Python-side merge) is
  hand-rolled where `VectorCypherRetriever` × 13 would have done the identical query
  with less code exposed to review, at the cost of a wrapper dependency for a call this
  simple. Low-priority future cleanup, not a correctness concern.

---

## References

- ADR-0001 — original `VectorCypherRetriever` mandate (amended to point here)
- ADR-0005 — per-label vector index naming/design rationale
- ADR-0007 — canonical LLM resolution (`api/dependencies.py::get_llm()`); this ADR does
  not revisit that decision
- ADR-0008 — hybrid retrieval mode, RRF design and constant, retrieval-mode ablation
- `backend/rag/retriever.py`, `backend/rag/graph_traversal.py` — actual implementation
- `neo4j_graphrag` v1.14.1 source, inspected directly:
  `neo4j_graphrag/retrievers/{vector,hybrid}.py`, `neo4j_graphrag/neo4j_queries.py`,
  `neo4j_graphrag/types.py::HybridSearchRanker`
- Cormack, G. V., Clarke, C. L. A., & Buettcher, S. (2009). *Reciprocal Rank Fusion
  outperforms Condorcet and individual rank learning methods.* SIGIR 2009. (already
  cited in ADR-0008; repeated here as the basis for rejecting `NAIVE`/`LINEAR`)
