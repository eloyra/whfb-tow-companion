# Plan — ADR-0009 (retriever architecture) + thesis text correction

**Status:** Not started
**Goal:** Two things, tightly scoped:
1. Close an already-flagged, never-written documentation gap: ADR-0007 explicitly lists
   "write a backend-RAG ADR covering retrieval (`rag/retriever.py`) and graph traversal
   (`rag/graph_traversal.py`) design, building on ADR-0001's `VectorCypherRetriever`
   mandate" as an open follow-up. It was never done. `docs/plans/
   baseline-showcase-graphrag.md` (an earlier planning doc) even already calls this out
   as "a documented ADR divergence" — except it isn't documented anywhere; that plan doc
   is the only place that says so.
2. Fix `docs/thesis/plantilla.tex` Section 5.5 and Table 5.3, which describe a design
   that was **abandoned early and never implemented**: they say the LLM provider is
   resolved via `llm/client.py`, and that retrieval uses `neo4j-graphrag`'s
   `VectorCypherRetriever`. Neither is true of the running system. `llm/client.py` is
   explicitly deprecated/unused per ADR-0007 (canonical path is
   `backend/api/dependencies.py::get_llm()`); `backend/rag/retriever.py`'s own docstring
   says it deliberately uses raw `db.index.vector.queryNodes()` calls instead of
   `VectorCypherRetriever`.

This plan is independent of the i18n plan and the graph-visualization plan — touches
only `docs/decisions/` and `docs/thesis/plantilla.tex`, zero shared files with those two.

**Explicitly out of scope** (belongs to other work, don't touch here):
- Section 5.6 (frontend graph-visualization claim) — becomes true once the
  graph-visualization plan lands; don't pre-emptively edit it.
- The Resumen's node/edge-count TODOs and validation-result TODOs (citation precision %,
  answer hit-rate %, Likert score) — separate gaps, unrelated to this one.
- Any code change. This plan is docs-only.

---

## Part 1 — `docs/decisions/ADR-0009-retriever-architecture.md` (new)

Follow the existing ADR template (see `ADR-0007-llm-provider-strategy.md` for the
closest-shaped precedent: it also documents "here's the divergence between what was
planned and what's actually running, and why").

**Context** section should state:
- ADR-0001 mandated `neo4j-graphrag`'s `VectorCypherRetriever` for retrieval (quote its
  exact rationale: "embed(query) → vector ANN over node.embedding → Cypher traversal of
  connected subgraph → context for LLM ... provided out of the box, with no custom
  orchestration code").
- What was actually built instead, and why (see Decision below) — this was a real
  engineering call made during implementation, not an oversight; the goal here is to
  write down the reasoning that already existed informally.

**Decision** section should describe the actual architecture as it exists today:
- `backend/rag/retriever.py::GraphRAGRetriever` — one HNSW vector index **per label**
  (13 of them, per `EMBEDDABLE_LABELS`), queried with raw `db.index.vector.queryNodes`
  and merged in Python by cosine score (not a single global index).
- `strategy="hybrid"` — full-text (BM25, single multi-label Neo4j fulltext index) fused
  with the vector ranking via Reciprocal Rank Fusion (see ADR-0008 — this ADR should
  reference and not duplicate ADR-0008's RRF details).
- `lexical_fallback` — an independent, optional exact-name-match boost.
- `backend/rag/graph_traversal.py::GraphTraversal` — `expand()` (bounded, per-relation-
  type-capped 1-hop neighborhood) and `links_between()` (direct seed-to-seed edges) as
  the traversal half of the pipeline, invoked separately from retrieval rather than
  fused into one `VectorCypherRetriever` call.
- The `RAG_MODE` ablation (ADR-0008: `vector`/`graph`/`hybrid`) that this custom design
  makes possible — this is the one-sentence "why it was worth diverging" payoff: none of
  `strategy`, `lexical_fallback`, `expand`, or the per-relation-type traversal caps are
  expressible through `VectorCypherRetriever`'s off-the-shelf API. A pre-built retriever
  class can't be an experimental ablation surface; the retrieval-mode comparison that
  Chapter 6 relies on for its central empirical result (does GraphRAG's advantage grow
  with hop count) would not have been possible without this custom implementation.
- LLM resolution — restate ADR-0007's already-correct decision
  (`api/dependencies.py::get_llm()`, `llm/client.py` deprecated) since Section 5.5 of the
  thesis currently contradicts it; this ADR can either fully own that restatement or
  simply cross-reference ADR-0007 or ADR-0007's decision verbatim — don't re-litigate it,
  just make sure Part 2 (thesis text) cites the correct ADR.

**Consequences** section: the accepted trade-off is exactly what ADR-0001 already
listed as a risk of *not* using the official package — more custom code to maintain,
no automatic upstream improvements to `neo4j-graphrag`. State plainly that this was
accepted deliberately in exchange for the ablation/fusion control above.

**References**: ADR-0001 (superseded retrieval mandate), ADR-0007 (LLM resolution,
already correct), ADR-0008 (RRF/hybrid mode design, don't duplicate),
`backend/rag/retriever.py`, `backend/rag/graph_traversal.py`.

## Part 2 — Amend `docs/decisions/ADR-0001-graph-database-selection.md`

Add a short amendment section (this repo's existing convention for ADR evolution — the
thesis itself describes an "adenda al ADR-0002" for the crawler's Next.js/Contentful
discovery, so amendments-in-place are the established pattern here, not a new one).
Something like:
```markdown
---

## Amendment (see ADR-0009)

The `VectorCypherRetriever`-based retrieval design mandated above was not implemented
as specified. The actual retrieval and traversal architecture — and the reasoning for
diverging — is documented in ADR-0009. This section is retained for historical context;
ADR-0009 is authoritative for how retrieval actually works.
```
Place it after the existing "## References" section, or wherever this file's existing
amendment convention (if any other ADR in this repo already has one — check
`ADR-0002-crawler-architecture.md`, referenced by the thesis text as having an "adenda")
puts it, for consistency.

## Part 3 — Correct `docs/thesis/plantilla.tex`

Search for these exact strings (don't rely on line numbers — another session/agent may
be editing this file concurrently, per the IDE having it open):

1. **Section 5.5 paragraph** (currently begins "El backend implementa el pipeline de
   recuperación híbrida GraphRAG..."). It currently contains, in order:
   - `"el proveedor de modelo de lenguaje se resuelve siempre a través de una capa de
     abstracción (\texttt{llm/client.py})"` → replace with a correct description: the
     provider is resolved via a registry function
     (`\texttt{api/dependencies.py::get\_llm()}`), configurable via the `LLM\_PROVIDER`
     env var; `\texttt{llm/client.py}` is a deprecated, unused earlier abstraction
     (cite ADR-0007).
   - `\texttt{TODO: proveedor y modelo de lenguaje finalmente seleccionados, con
     justificación breve de la elección}` → fill with the actual answer: **Anthropic**
     (Claude, model `claude-sonnet-5` by default, configurable via `LLM\_MODEL`).
     Justification grounded in real code, not post-hoc: `backend/rag/tools.py`'s
     `use_native_citations()` switch and the whole `search_result`-content-block /
     `search_result_index` citation machinery in that file exist *specifically* for
     Anthropic's native citation support — i.e. the citation-verifiability requirement
     that is one of this thesis's two central objectives (Section 3.2) is best served on
     the Anthropic path, which is the concrete reason to name it as the selected
     provider rather than a default-by-inertia choice.
   - `"El pipeline se apoya en la clase \texttt{VectorCypherRetriever} del paquete
     oficial \texttt{neo4j-graphrag}... sin código de orquestación adicional para el
     bucle de recuperación."` → replace with an accurate description of
     `GraphRAGRetriever` + `GraphTraversal` (per-label HNSW ANN, optional hybrid
     BM25+RRF fusion, optional lexical fallback, bounded per-relation-type-capped
     traversal) and cite the new ADR-0009 for the full rationale, rather than repeating
     it at length in the prose — this section should summarize, ADR-0009 is where the
     detail lives.

2. **Table 5.3 ("Pila tecnológica del backend y el frontend")**, row "Proveedores LLM":
   cell currently reads `\texttt{TODO: proveedor final}` → `\texttt{Anthropic (Claude)}`.
   Consider whether the adjacent "Notas" cell ("Abstracción configurable sobre OpenAI /
   Anthropic / Ollama mediante variable de entorno") still needs the `llm/client.py`
   correction too — check it doesn't also mis-cite that module.

3. **Table 5.2 ("Pila tecnológica de la base de datos de grafo y los embeddings")**, row
   "Paquete GraphRAG": cell currently reads `\texttt{neo4j-graphrag}` /
   `\texttt{VectorCypherRetriever} para búsqueda por similitud (ANN) y recorrido Cypher`.
   This table is titled around the *stack*, not just what was planned — decide whether
   to remove this row entirely (the package isn't actually used) or repoint it at the
   real stack (`neo4j` official driver's `db.index.vector.queryNodes` procedure calls,
   no `neo4j-graphrag` package dependency). Removing/replacing this row is likely
   cleaner than adding another ADR-0009 citation inline — this is a tech-stack listing
   table, keep it factual and terse.

4. **Resumen** (Chapter 1, near the top): `\texttt{TODO: especificar el modelo de
   lenguaje finalmente seleccionado (OpenAI, Anthropic u Ollama) una vez cerrada la
   decisión}` → fill with the same answer as item 1 above (Anthropic/Claude Sonnet 5),
   phrased to fit the Resumen's summary register — no need to repeat the full
   justification here, that belongs in Chapter 5.

Do **not** touch anything else in the Resumen paragraph (node/edge counts, validation
percentages, Likert score, conclusion) — those TODOs belong to other, separate gaps.

## Verification

1. Grep the corrected file for the strings above to confirm none remain:
   `grep -n "VectorCypherRetriever\|llm/client.py\|TODO: proveedor" docs/thesis/plantilla.tex`
   — the only acceptable remaining hits, if any, should be inside ADR cross-references
   you intentionally added, not the original claims.
2. Diff the changed paragraphs against `backend/rag/retriever.py`,
   `backend/rag/graph_traversal.py`, and `backend/api/dependencies.py::get_llm()` one
   more time — every technical claim in the corrected text should be directly traceable
   to a real file/function, not a restatement of intent.
3. If a LaTeX toolchain is available locally (check for `pdflatex`/`latexmk` on PATH; if
   not, skip this step and say so rather than guessing), compile
   `docs/thesis/plantilla.tex` and confirm no new errors were introduced by the edit.
4. Confirm the new `ADR-0009-retriever-architecture.md` file follows the existing ADR
   frontmatter table format (Status/Date/Deciders/Tags) used by every other file in
   `docs/decisions/`, and that `docs/CLAUDE.md`'s ADR table gets a new row for it
   (mirroring how ADR-0008 was added there this session).
