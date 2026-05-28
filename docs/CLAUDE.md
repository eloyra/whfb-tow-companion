# CLAUDE.md — docs/

Scoped context for the `docs/` directory.
For project overview and coding conventions, see [`../CLAUDE.md`](../CLAUDE.md).

---

## What lives here

| Directory | Status | Notes |
|---|---|---|
| `decisions/` | Binding | Architecture Decision Records (ADRs) |
| `schema/` | Authoritative | Knowledge graph node/edge schema |
| `diagrams/` | Reference | Architecture and flow diagrams |
| `plans/` | Non-binding | Planning artefacts, may be stale |

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

---

## Schema is authoritative

`schema/knowledge_graph_schema.md` defines all node types, edge types, and property contracts.
Any change to node shape, a new edge type, or a new node label must be reflected here first.
