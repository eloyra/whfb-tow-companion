# CLAUDE.md — pipeline/

Scoped context for the data pipeline (scrape → parse → graph → embeddings → i18n).
For project overview, stack, environment variables, and coding conventions, see [`../CLAUDE.md`](../CLAUDE.md).

---

## What lives here

| Directory | Purpose |
|---|---|
| `scraper/` | BFS crawler + per-section parsers |
| `markdown/` | `exporter.py` — converts rendered DOM (not Contentful JSON) into a URL-mirrored markdown corpus in `data/markdown/`; opt-in stage, not part of `--all` |
| `graph/` | Neo4j graph builder, loader, validator (`serializer.py` is a `# TODO` stub, unused) |
| `embeddings/` | Sentence-transformer embedding generation (per-label text builders + HNSW vector_store) |
| `i18n/` | Translation injection into graph nodes (`translator.py` is a `# TODO` stub) |
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
| Parser data-source strategy | `docs/decisions/ADR-0006-parser-data-source-strategy.md` |

---

## Current pipeline state

*(Last updated: 2026-07-14)*

| Stage | Status |
|---|---|
| Scrape | Done — dual-seed BFS, output in `data/raw/` (~2,720 HTML files, all 19 armies) |
| Markdown export | Done — `markdown/exporter.py`; opt-in stage (`make markdown`, not in `--all`), output in `data/markdown/` mirroring URL paths; converts rendered DOM, not the Contentful JSON `parse` stage reads |
| Parse | Done — nodes and edges in `data/parsed/` (18 JSON files per ADR-0004); see gaps below |
| Graph build | Done — graph loaded into Neo4j; `load_report.json` in `data/graph/` |
| Embeddings | Done — `generator.py`, `text.py` (13 per-label builders), `vector_store.py` (HNSW per-label indexes); wired into `run_pipeline.py` |
| Translations | Done — `i18n/translator.py` implements `Translator`, mirroring `EmbeddingGenerator`; writes flat `name_es`/`text_es` via a local Ollama model (no paid API); `translations/es.json` is a translation-memory cache, not a data store |

Remaining stubs in this subtree: `graph/serializer.py` (1-line `# TODO`, not imported by the builder).

Known gaps (deferred, not bugs):
- Champion magic-item budget **not profile-scoped** — `points_budget` is 0 / `None` on
  `command_champion` upgrades; budgets live as separate `magic_item_budget` nodes granted to
  the Unit, not the champion sub-profile.
- Standard-bearer `magic_standard_budget` — dispatch reorder not shipped; property exists
  only as separate `magic_standard_budget` nodes, not on `command_standard` upgrades.
- `armour_value` (shield, armour pages) — no `profile-table--weapon` column on armour pages;
  apply canonical schema seed values (`docs/schema/knowledge_graph_schema.md:775-779`).
- War-machine `shots` / `template_type` / `bounce` / `is_indirect` — no
  `/weapons-of-war/cannon` page (cannon is a `:Unit`); needs unit-prose parse or manual seed.
- `casting_value_boosted` — rendered spell stat table has only one Casting Value row; no
  structured source for the boosted value.
- Weapon `special_rules` → slugs when table cell is plain text (no `<a href>`) — name-match
  fallback only.
- `_options.py` typed-href rework — deferred; two-pass UNLOCKS relabel is working and
  sufficient.
- `text_es` mirrors the post-`embed` `n.text` (the enriched graph-context blob), so
  re-running `embed` after `translate` makes `text_es` stale — the `name_es IS NULL`
  filter only detects untranslated nodes, not changed `text`. Re-run `translate` again
  after any `embed` re-run.

HTML-extraction rationale: see `docs/decisions/ADR-0006-parser-data-source-strategy.md` and
`docs/plans/scraper-html-pivot-explained.md`.

Shipped (verified in live graph):
- Dedicated `/magic-item/{slug}` pages (731, singular URL) were routed to `CoreRuleParser`
  by the manifest's generic `core_rule` fallback — same bug class as the `/spell/` collision
  fixed in ADR-0006, undetected until now. Produced a same-id `CoreRule` node for every
  `MagicItem`, so any labelless `MATCH (n {id: ...})` (e.g. `pipeline/rag/pipeline.py`
  context enrichment) could non-deterministically resolve to the wrong node. Fixed with a
  `parsers/__init__.py` routing override (mirroring `/spell/`) and a `MagicItemParser`
  branch for the dedicated single-entry page shape (`entry.sys.contentType.sys.id ==
  "magicItem"`, fields identical to one list-page item entry). Also recovered 33 magic items
  that only ever existed on a dedicated page, never in a listing embed, and — since
  `MagicItemParser` had never emitted `REFERENCES` edges at all (unlike
  `rule_parser.py`/`spell_parser.py`/`weapon_parser.py`) — added that extraction too,
  recovering 1,262 `REFERENCES` edges that the phantom `CoreRule` nodes had been
  accidentally carrying under the wrong node identity. Verified: 0 MagicItem/CoreRule
  id collisions (was 731); `CoreRule` 1,377→646, `MagicItem` 698→731 nodes;
  `REFERENCES` 6,031→4,786 edges after full wipe+rebuild. `CAN_TAKE_ITEM` also dropped
  73,321→45,733 as a side effect of the first true full wipe in a long time — MERGE-based
  rebuilds never delete stale edges, so that figure had been accumulating cruft across
  the project's history; 45,733 is the first count reflecting only current derivation logic.
- `SPLIT_PROFILE_OF` — 155 edges (mount-profile heuristic: M present, T+W absent)
- `HAS_COMPOSITION_RULE` — 17 edges (Army → army-list CoreRule page)
- `PART_OF_SECTION` — 77 edges
- Weapon `range` / `strength` / `ap` — from `table.profile-table--weapon`; 226 weapons with
  `range IS NOT NULL`
- Spell `casting_value` / `range` / `spell_type` — via dedicated `/spell/{slug}` pages
  (`SpellParser`); lore pages handled by `LoreParser` (membership only); 139 / 139 spells
  have `spell_type`
- `TERRAIN_INTERACTION` — 9 edges written by seed; 37 `:Terrain` nodes in graph
- `CLARIFIES` / `AMENDS` — 510 / 407 edges at 83–88% coverage
- `HAS_INTRINSIC_RULE` — 80 edges
- `:Terrain` embedding text builder (`text.py::_build_terrain`) — previously
  `Terrain` was listed in `EMBEDDABLE_LABELS` with no dedicated builder, so a
  fresh `make embed` would have silently regressed every `:Terrain` node's
  `text` to its bare name (`_build_name_only` fallback), destroying the body
  text and terrain-class/movement flags used for citations. Verified against
  the live `tow.whfb.app` battlefield-terrain pages before fixing; all 37 live
  nodes re-embedded with class + movement-flag summary + body text.
- `:Unit` embedding text now surfaces `Upgrade.availability_constraint`
  (e.g. `"[0-1 unit in your army may]"`) — this army-composition-legal text
  was parsed and stored on `:Upgrade` nodes but was unreachable by the agent
  (not in the `:Unit` upgrade rollup, and `:Upgrade` is intentionally not
  embedded independently per the ADR-0005 amendment). Verified against a live
  unit page (`bestigor-herd`) before fixing; all 574 `:Unit` nodes re-embedded.
- `MagicItem.army_id` for Arcane Journal supplements now normalised to a real
  `:Army.id` (`ARCANE_JOURNAL_ASSOCIATION_ARMY_MAP` /
  `ARCANE_JOURNAL_PAGE_ARMY_OVERRIDES` in `pipeline/constants.py`) — the raw
  Contentful association slug (e.g. `"arcane-journal-dwarfen-mountain-holds"`)
  never matched any `:Army.id`, so `GraphBuilder._derive_can_take_item`
  (`i.army_id = a.id`) silently produced **zero** `CAN_TAKE_ITEM` edges for
  every Dwarf Rune item against all 29 `rune_budget` upgrades, and for Tomb
  Kings' Nehekharan scrolls. One Arcane Journal book ("The War of Settra's
  Fury") turned out to cover two unrelated armies on different pages; verified
  against the live magic-items pages before mapping. Now 17 Rune items / 217
  edges and 6 scroll items / 90 edges reachable.
- `Unit.wizard_level` was stored as a **string** (Contentful serialises it as
  `"3"`, not `3`), so `coalesce(u.wizard_level, 0) >= 1` in
  `_derive_can_take_item` always evaluated to null/false — every single
  `arcane_item`-type `:MagicItem` (82 total) was unreachable via
  `CAN_TAKE_ITEM` for every wizard character in every army. Fixed with an
  explicit `int()` cast in `UnitParser` (mirrors the existing `unitSize`
  handling). Verified against the live `archmage.html` fixture before fixing.
  Now all 82 arcane items are reachable (2,828 edges); the Archmage alone
  reaches 59 of them.

---

## Scraper rules

- Always read `SCRAPE_DELAY_SECONDS` from env (default 1.0) — never hardcode a delay
- Base URL from `SCRAPE_BASE_URL` env var — never hardcode `https://tow.whfb.app`
- The wiki is static HTML; `requests` + `beautifulsoup4` only, no headless browser
- Content routing: magic-item rules pages → `CoreRuleParser`, not `MagicItemParser`
