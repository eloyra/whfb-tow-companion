# ADR-0004 — Parse Output Contract: File Format

| Field       | Value                          |
|-------------|--------------------------------|
| **Status**  | Amended (bridging section superseded 2026-04-14; graph-safe shapes added 2026-04-24) |
| **Date**    | 2026-04-14                     |
| **Amended** | 2026-04-24                     |
| **Deciders**| Project author                 |
| **Tags**    | pipeline, parsers, graph-builder, data-format |

---

## Context

The scraper pipeline is split into two stages:

1. **Scrape** (`make scrape`) — the crawler fetches raw HTML and writes it to `data/raw/`.
2. **Parse** (`make parse`) — parsers read raw HTML and produce structured JSON in `data/parsed/`.

The graph builder (`make build-graph`) then reads `data/parsed/` and constructs the Neo4j knowledge graph.

This ADR documents the exact contract between the parse stage and the graph builder so that the two stages can be developed and modified independently.

---

## Decision

### Output file layout

`data/parsed/` contains one JSON file per node type plus a shared edges file:

| File | Node type | Notes |
|------|-----------|-------|
| `armies.json` | `Army` | One object per army page |
| `units.json` | `Unit` | Profiles extracted to `profiles.json`; all nested maps flattened |
| `profiles.json` | `Profile` | Stat sub-profiles (rider/mount/champion); see amendment 2026-04-24 |
| `special_rules.json` | `SpecialRule` | Universal and army-specific special rules |
| `core_rules.json` | `CoreRule` | Rulebook mechanics pages |
| `troop_types.json` | `TroopType` | `/troop-types-in-detail/` pages |
| `weapons.json` | `Weapon` | `/weapons-of-war/` pages |
| `spells.json` | `Spell` | Extracted from lore pages (multiple per page) |
| `lores.json` | `Lore` | Magic lore pages |
| `magic_items.json` | `MagicItem` | Extracted from magic-items pages |
| `faqs.json` | `FAQ` | Q&A entries |
| `errata.json` | `Errata` | Correction entries |
| `documents.json` | `Document` | Orientation / etiquette wiki pages |
| `edges.json` | *(edges)* | All directed edges across all node types |

Every file is a JSON array.  An empty array is valid (no content of that type was found).

### Node object format

Every node object in the output files matches the schema in
`docs/schema/knowledge_graph_schema.md`.  The `node_type` key is **stripped**
before writing — it was used internally by the coordinator to route records to
the correct file.

### Edge object format

```json
{
  "src":        "blood-knights",
  "dst":        "fear",
  "relation":   "HAS_RULE",
  "properties": {}
}
```

`src` and `dst` are node slugs (the `id` field of the referenced nodes).
`relation` is one of the `EdgeType` constants from `pipeline/constants.py`.
`properties` is a dict of optional edge attributes (may be empty).

---

## ~~The unit-profile bridging problem~~ — SUPERSEDED

> **Amendment (2026-04-14):** The bridging section below was written before the
> site was re-inspected at the `__NEXT_DATA__` level (see ADR-0002 addendum and
> ADR-0003 addendum).  It is retained for historical context but is **no longer
> implemented**.  Do not use it as a guide for the graph builder.

### Why it no longer applies

Unit stat profiles (M / WS / BS / S / T / W / I / A / Ld) **are** present on
individual unit pages in the `__NEXT_DATA__` JSON blob.  The Contentful
`armyListEntry` content type embeds the full `unitProfile` array directly on
each `/unit/{slug}` page:

```json
"unitProfile": [
  {"Name": "Blood Knight", "M": "–", "WS": "5", "BS": "3", "S": "4",
   "T": "4", "W": "1", "I": "4", "A": "2", "Ld": "7"},
  {"Name": "Kastellan", ...},
  {"Name": "Nightmare", "M": "7", ...}
]
```

`UnitParser` parses this array directly and stores it in the `Unit` node's
`profiles` field.  No cross-page join is needed.  `unit_profiles.json` is
**not written**, and the graph builder does **not** need a merge step.

### Historical context (original bridging design)

The original design assumed stats were only available in the HTML stat table on
the army page — a flat `<table>` keyed by unit display name.  This would have
required:

1. `ArmyParser` extracting stats → `unit_profiles.json` keyed by `unit_slug_hint`.
2. The graph builder fuzzy-matching `unit_slug_hint` → canonical `unit.id`.
3. A fallback for unmatched hints (create minimal Unit node from profile data).

This design was rejected once the actual data source was confirmed.

---

## Consequences

### Positive
- Parsers remain stateless: each parser processes one HTML file and returns a
  `ParseResult` with no dependency on other pages.
- Unit nodes in `units.json` are complete and self-contained — the graph
  builder can create `Unit` nodes in Neo4j directly from this file with no
  joins or fuzzy matching.
- The output contract is simpler: 10 node files + 1 edge file.

### Negative / accepted trade-offs
- If the wiki ever moves stat profiles off the unit page (e.g. behind a
  JavaScript-rendered component), `UnitParser` would silently produce units
  with empty `profiles: []`.  The crawler already logs warnings for empty
  parsed results, providing a detection mechanism.

---

---

## Amendment — Parse-time normalisation for graph-safe shapes (2026-04-24)

### Problem

Neo4j node properties must be scalars or lists of scalars.  The original parse
output contained nested maps (`source_citation`, `base_size_mm`, `unit_size`,
`profiles`) and a raw `i18n` dict.  Attempting to `SET n += row` with such a
record fails at load time with a Neo4j type-constraint error.

### Decision

All schema normalisation is the **parsers' responsibility**, not the loader's.
The loader is a pure MERGE stage — it sets node properties directly from the
parsed record without any transformation.

Specifically:

#### Scalar-map flattening

Nested maps are replaced by scalar columns using `**` spread syntax in every
parser:

| Original key | Replacement columns |
|---|---|
| `source_citation: {book, page}` | `source_citation_book`, `source_citation_page` |
| `base_size_mm: {width, depth}` | `base_width_mm`, `base_depth_mm` |
| `unit_size: {min, max}` | `unit_size_min`, `unit_size_max` |

These transforms live in `BaseParser._make_source_citation()`,
`BaseParser._parse_base_size()`, and `BaseParser._parse_unit_size()` and are
called via `**self._make_source_citation(...)` spread in every parser's node
constructor.

#### i18n → per-language scalar columns

The raw `i18n` dict is dropped from all node records.  Non-English translations
are stored as `{field}_{lang}` columns (e.g. `name_es`, `text_es`).  English
fields are canonical and remain top-level.

`BaseParser._make_i18n()` currently returns `{}` because the translate stage
has not run yet; it will be populated when `make translate` fills Spanish
columns.  Frontend code reads `coalesce(n.name_es, n.name)` to display the
correct language.

#### Profiles as first-class nodes

`profiles[]` is removed from `Unit` records.  For each profile in `unitProfile`,
`UnitParser` emits:

- A `Profile` node record (in `profiles.json`) with:
  - `id`: `{unit-slug}#{profile-name-slug}`
  - All nine stat columns (`M`, `WS`, `BS`, `S`, `T`, `W`, `I`, `A`, `Ld`) as
    scalars (`int | None`)
  - `order`: integer position in the original profile array
- A `HAS_PROFILE` edge from the unit to the profile node, with `order` as an
  edge property.

This enables Cypher stat queries like:
```cypher
MATCH (u:Unit)-[:HAS_PROFILE]->(p:Profile) WHERE p.WS >= 5 AND p.A >= 3
RETURN u.name, p.name, p.WS, p.A
```

### Consequences

- The loader (`pipeline/graph/loader.py`) stays at ~30 lines: UNWIND + MERGE +
  `SET n += row`, with no conditional logic.
- Any parse-time transform bug produces incorrect data in `data/parsed/`; a
  re-run of `make parse` fixes it without touching the graph layer.
- `profiles.json` is a new required output file; the coordinator routes records
  with `node_type="profile"` to it.

---

## References

- `pipeline/scraper/parsers/unit_parser.py` — produces `units.json` with profiles
- `pipeline/scraper/parsers/__init__.py` — coordinator that writes output files
- ADR-0002 addendum — Next.js / Contentful architecture discovery
- ADR-0003 addendum — revised unit data model
