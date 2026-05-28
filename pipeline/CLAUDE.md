# CLAUDE.md — pipeline/

Scoped context for the data pipeline (scrape → parse → graph → embeddings → i18n).
For project overview, stack, environment variables, and coding conventions, see [`../CLAUDE.md`](../CLAUDE.md).

---

## What lives here

| Directory | Purpose |
|---|---|
| `scraper/` | BFS crawler + per-section parsers |
| `graph/` | Neo4j graph builder, serializer, validator |
| `embeddings/` | Sentence-transformer embedding generation |
| `i18n/` | Translation injection into graph nodes |
| `constants.py` | Single source of truth — node/edge types, mappings |
| `run_pipeline.py` | CLI entry point for end-to-end run |

---

## `constants.py` is authoritative

Before adding any node type, edge type, or vocabulary mapping, check `constants.py` first:

- `NodeType` — all valid node labels
- `EdgeType` — all valid relationship types
- `CHARACTERISTIC_MAP` — stat abbreviation → `CoreRule` node ID (avoids ~1800 redundant edges)
- `MAGIC_ITEM_TYPE_MAP` — normalises `item_type` to snake_case
- `TROOP_TYPE_SEED` — canonical TroopType node data (rank bonus, unit strength)
- `SUPPORTED_LANGUAGES` — only `en` and `es` exist today

Never hardcode a node type string like `"Unit"` or an edge type like `"HAS_RULE"` — always use the enum.

---

## Parse output contract (ADR-0004)

Parsers write to `data/parsed/`. Each file is a JSON object with two arrays:

```json
{ "nodes": [...], "edges": [...] }
```

Node shape (all fields present, missing values as `null`):

```json
{
  "id": "<url-slug>",
  "node_type": "<NodeType value>",
  "url": "https://tow.whfb.app/<path>",
  "source_citation": { "book": "<name>", "page": <int|null> },
  "i18n": {
    "en": { "name": "...", "text": "..." },
    "es": { "name": "...", "text": "..." }
  }
}
```

Edge shape:

```json
{
  "source": "<node-id>",
  "target": "<node-id>",
  "edge_type": "<EdgeType value>"
}
```

Key rules:
- `id` is always the URL slug (e.g. `"blood-knights"`, `"fear"`)
- Stats use `null` for `-` (characteristic not applicable) — never `"-"` or `0`
- `source_citation` is always an object, even when page is unknown (`{ "book": "...", "page": null }`)
- English is the canonical language; `i18n.es` populated by the `i18n/` stage, not the parsers

---

## Design decisions to read before modifying

| Component | ADR |
|---|---|
| Crawler architecture | `docs/decisions/ADR-0002-crawler-architecture.md` |
| Army-page data strategy | `docs/decisions/ADR-0003-army-page-data-strategy.md` |
| Parse output contract | `docs/decisions/ADR-0004-parse-output-contract.md` |
| Graph storage conventions | `docs/decisions/ADR-0005-graph-storage-conventions.md` |
| Graph database selection | `docs/decisions/ADR-0001-graph-database-selection.md` |

---

## Current pipeline state

*(Last updated: 2026-05-27)*

| Stage | Status |
|---|---|
| Scrape | Done — dual-seed BFS, output in `data/raw/` |
| Parse | Done — nodes and edges in `data/parsed/`; see gaps below |
| Graph build | Done — graph loaded into Neo4j; `load_report.json` in `data/graph/` |
| Embeddings | Pending |
| Translations | Pending |

Known gaps (deferred, not bugs):
- `SPLIT_PROFILE_OF` edges for multi-profile units — not emitted (Fix 2 in fix plan)
- `HAS_COMPOSITION_RULE` edges from Army to its list page — not emitted (Fix 6 in fix plan)
- Weapon `range` / `strength` / `ap` fields — populated from `table.profile-table--weapon` (Fix 7 done)
- Spell `casting_value` / `range` / `spell_type` — fully structured; dedicated `/spell/{slug}` pages
  are the source of truth via `SpellParser`; lore pages handled by `LoreParser` (Fix 7 done)
- `Upgrade` nodes — present but champion `points_budget` and standard-bearer `magic_standard_budget`
  not correctly captured (Fixes 3 + 4 in fix plan)
- `TERRAIN_INTERACTION` edges from seed — enabled but unverified in live graph (Fix 5)

Previously listed as gaps, now shipped:
- ~~`Terrain` nodes~~ — 37 `:Terrain` nodes parsed and in graph (Fix 1 done)
- ~~`CLARIFIES`/`AMENDS` edges~~ — 517 / 441 edges at 83–88% coverage
- ~~`HAS_INTRINSIC_RULE` edges~~ — 80 edges in graph

---

## Scraper rules

- Always read `SCRAPE_DELAY_SECONDS` from env (default 1.0) — never hardcode a delay
- Base URL from `SCRAPE_BASE_URL` env var — never hardcode `https://tow.whfb.app`
- The wiki is static HTML; `requests` + `beautifulsoup4` only, no headless browser
- Content routing: magic-item rules pages → `CoreRuleParser`, not `MagicItemParser`
