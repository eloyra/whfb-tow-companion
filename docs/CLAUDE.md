# CLAUDE.md — docs/

Scoped context for the `docs/` directory.
For project overview and coding conventions, see [`../CLAUDE.md`](../CLAUDE.md).

---

## What lives here

| Path | Status | Notes |
|---|---|---|
| `decisions/` | Binding | Architecture Decision Records (ADRs), including amendments |
| `schema/` | Authoritative | Knowledge graph node/edge schema (v3.1; re-aligned with ADR-0004/0005 amendments) |
| `diagrams/` | Empty / pending | Architecture and flow diagrams — not yet produced |
| `plans/` | Non-binding | Planning artefacts, may be stale |
| `validation/` | Non-binding | Graph-validation tracker, query-coverage seed, conformity reports (currently empty) |
| `architecture-and-chat-review.md` | Non-binding | One-off review of backend chat + frontend architecture |
| `partial-deliverable-briefing.md` | Non-binding | TFM deliverable briefing notes |
| `warhammer_tow_domain_knowledge.md` | Reference | Domain knowledge dump used for prompt/evaluation context |
| `demo-queries.cypher` | Reference | Example Cypher queries for demos |

---

## ADRs are binding

Read the relevant ADR **before** working on any component it covers.
Each ADR records what was decided, why, and what alternatives were rejected.
Do not re-litigate closed decisions unless the user explicitly overrides them.

Current ADRs:

| File | Covers |
|---|---|
| `ADR-0001-graph-database-selection.md` | Why Neo4j over alternatives |
| `ADR-0002-crawler-architecture.md` | Dual-seed BFS, politeness, retry |
| `ADR-0003-army-page-data-strategy.md` | How army/unit pages are parsed |
| `ADR-0004-parse-output-contract.md` | JSON shape out of parsers |
| `ADR-0005-graph-storage-conventions.md` | Node IDs, property names, index design |
| `ADR-0006-parser-data-source-strategy.md` | Hybrid parsing (Contentful JSON + HTML DOM), spell source-of-truth |
| `ADR-0007-llm-provider-strategy.md` | Canonical LLM resolution via `api/dependencies.py`; `llm/client.py` deprecated |
| `ADR-0008-retrieval-modes.md` | `RAG_MODE` retrieval-mode ablation (vector / graph / hybrid); RRF fusion, full-text index |
| `ADR-0009-retriever-architecture.md` | Actual retriever/traversal design vs. ADR-0001's superseded `VectorCypherRetriever` mandate; why `neo4j-graphrag`'s retrievers were evaluated and rejected |

---

## Schema is authoritative

`schema/knowledge_graph_schema.md` defines all node types, edge types, and property contracts.
Any change to node shape, a new edge type, or a new node label must be reflected here first.
