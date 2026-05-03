# ADR-0005 — Graph Storage Conventions

| Field       | Value                          |
|-------------|--------------------------------|
| **Status**  | Accepted                       |
| **Date**    | 2026-04-24                     |
| **Deciders**| Project author                 |
| **Tags**    | graph, neo4j, embeddings, docker, storage |

---

## Context

ADR-0001 selected Neo4j as the graph database and established the GraphRAG
retrieval architecture.  That ADR left several implementation-level decisions
open:

- How to deploy Neo4j locally and in CI.
- How to represent node properties that Neo4j's type system does not support
  natively (nested maps, list-of-maps).
- Whether to embed unit stat profiles as a JSON blob or as graph nodes.
- How to handle multilingual content in embeddings.
- How to structure vector indexes for label-scoped ANN queries.

This ADR records those decisions.

---

## Decision

### 1 — Docker-based Neo4j 5.x deployment

Neo4j is run via Docker Compose (`docker/docker-compose.yml`) using the official
`neo4j:5.24-community` image with the APOC plugin.  Named volumes (`neo4j_data`,
`neo4j_logs`) persist data across container restarts.

Rationale: Community Edition is free and includes the built-in HNSW vector index
introduced in Neo4j 5.x.  APOC is required for `apoc.merge.relationship`, which
enables dynamic relation types in the edge-loading UNWIND batch.

Makefile targets:

| Target | Effect |
|---|---|
| `make neo4j-up` | Start container, wait for healthcheck |
| `make neo4j-down` | Stop container (data preserved) |
| `make neo4j-reset` | Stop and delete volumes (destructive) |
| `make neo4j-logs` | Stream container logs |

### 2 — Parse-time property flattening (graph-safe shapes)

Neo4j node properties must be scalars or homogeneous lists of scalars.  All
nested-map and list-of-map fields are flattened to scalar columns **at parse
time**, before the JSON hits `data/parsed/`.

Full normalisation rules are documented in ADR-0004 (2026-04-24 amendment).
Summary:

| Before (parse output) | After (node property) |
|---|---|
| `source_citation: {book, page}` | `source_citation_book`, `source_citation_page` |
| `base_size_mm: {width, depth}` | `base_width_mm`, `base_depth_mm` |
| `unit_size: {min, max}` | `unit_size_min`, `unit_size_max` |
| `i18n: {en: {...}, es: {...}}` | `name_es`, `text_es`, etc. (English stays top-level) |
| `profiles: [{...}, ...]` | Separate `:Profile` nodes (see §3) |

The loader (`pipeline/graph/loader.py`) remains a pure MERGE stage:
`UNWIND $rows AS row MERGE (n:Label {id: row.id}) SET n += row`.

### 3 — Profiles as first-class graph nodes

Unit stat sub-profiles (rider / mount / champion) are stored as `:Profile` nodes
connected to their parent unit via `HAS_PROFILE` edges.

**Rejected alternative — JSON blob:** Encoding profiles as a JSON-serialised
string property (e.g. `n.profiles_json`) would allow storage but would make stat
comparisons impossible in Cypher.  A query like "find units where WS ≥ 5 and
A ≥ 3" would require deserialising JSON in application code across all nodes —
defeating the purpose of having a graph database.

**Chosen design:**

```cypher
MATCH (u:Unit)-[:HAS_PROFILE]->(p:Profile)
WHERE p.WS >= 5 AND p.A >= 3
RETURN u.name, p.name, p.WS, p.A
ORDER BY u.name
```

Profile node schema:
- `id`: `{unit-slug}#{profile-name-slug}` (e.g. `blood-knights#kastellan`)
- Stats: `M`, `WS`, `BS`, `S`, `T`, `W`, `I`, `A`, `Ld` — all `int | None`
- `order`: integer position in the original profile array (used for ordering)
- `name`: profile sub-type name (e.g. "Kastellan", "Nightmare")

`HAS_PROFILE` edge carries `order` as an edge property for `ORDER BY` without
re-fetching the node.

Profile nodes are **not embedded** directly — they are captured inside their
parent unit's embedding text, which includes the full stat block.

### 4 — i18n per-language scalar columns

The raw `i18n: {en: {...}, es: {...}}` dict is dropped from all node records.
Translations are stored as `{field}_{lang}` scalar columns (e.g. `name_es`,
`text_es`).  English is canonical and stays top-level (`name`, `text`).

Frontend code reads `coalesce(n.name_es, n.name)` for the user's preferred
language.  The translate stage (`make translate`) fills `name_es` / `text_es`
columns after the graph is built.

Until the translate stage runs, all `_{lang}` columns are absent (null) on every
node.

### 5 — Embedding strategy

#### Single English vector per node

One 768-dimensional vector (`n.embedding`) per node, generated from
English-language text.  No `n.embedding_es` column.

Rationale: the chosen model (`paraphrase-multilingual-mpnet-base-v2`) is trained
on 50+ languages and maps semantically equivalent text from different languages
to nearby regions of the same embedding space.  A Spanish query "caballería
rápida con muchos ataques" will find the English `Blood Knights` node without
translation, because the Spanish and English tokens land near the same centroid.
Storing per-language vectors would triple storage and index size for zero
retrieval quality gain.

#### Graph-context embedding text

Embedding text is built **after the graph is loaded**, by querying the graph for
each node's neighbors.  This produces denser, more semantically rich text than
serialising the raw JSON record.

Example for a `:Unit` node:
```
Blood Knights. Vampire Counts. Heavy Cavalry. Rare. 39 pts/model.
Unit size 5+. Base 30x60mm.
Profiles — Blood Knight: M8 WS5 BS3 S4 T4 W1 I4 A2 Ld7;
            Kastellan: M8 WS5 BS3 S4 T4 W2 I4 A3 Ld8.
Rules: Fear, Frenzy. Weapons: Lance, Heavy Armour.
```

Per-label text builders live in `pipeline/embeddings/text.py`.

#### Resumable embedding

Nodes are embedded in batches.  The query
`MATCH (n:Label) WHERE n.embedding IS NULL` makes the process resumable —
re-running `make embed` skips already-embedded nodes.

### 6 — Per-label vector indexes

One HNSW vector index per embeddable label, named `<snake_label>_embedding_idx`
(e.g. `special_rule_embedding_idx`, `unit_embedding_idx`).

Rationale: Neo4j 5.x vector indexes are per-label-per-property.  Per-label
scoping enables cheap label-scoped ANN queries from `VectorCypherRetriever`
(ADR-0001):

```cypher
CALL db.index.vector.queryNodes('unit_embedding_idx', 10, $queryVec)
YIELD node, score
RETURN node.name, score
```

A single cross-label index would force post-hoc label filtering, wasting ANN
budget on irrelevant node types.

Index parameters:
- Dimensions: 768 (matches `paraphrase-multilingual-mpnet-base-v2`)
- Similarity function: cosine
- Indexes created **after** at least one embedding exists on nodes of each label
  (Neo4j ignores the property type hint until populated nodes are present)

Embeddable labels: `Army`, `Unit`, `SpecialRule`, `CoreRule`, `Document`,
`TroopType`, `Spell`, `MagicItem`, `Lore`, `Weapon`, `FAQ`, `Errata`.

`:Profile` is **not embedded** independently — stat data is captured inside the
parent `:Unit` embedding text.

---

## Consequences

### Positive

- Loader stays simple (pure MERGE, no transforms).
- Cypher stat queries work cleanly on `:Profile` nodes.
- Semantic search across 12 label types with cheap label-scoped ANN.
- Spanish queries work without separate translation of query or storage of
  Spanish embeddings.
- Re-running any pipeline stage is idempotent (MERGE + `WHERE n.embedding IS NULL`).

### Negative / accepted trade-offs

- `:Terrain` nodes do not exist yet; terrain seed writes zero edges (expected,
  logged as info, not error).
- APOC is required for dynamic relation types in edge loading.  Without APOC,
  each relation type needs a separate hardcoded Cypher statement.
- Profile nodes roughly double the total node count (~945 profiles for ~475
  units).  This is acceptable given the graph size and query value.

---

## References

- `pipeline/graph/builder.py` — orchestrator
- `pipeline/graph/loader.py` — MERGE-based node and edge loader
- `pipeline/graph/ddl.py` — constraints + btree + vector DDL
- `pipeline/embeddings/text.py` — per-label embedding text builders
- `pipeline/embeddings/vector_store.py` — vector index creation
- `docker/docker-compose.yml` — Neo4j container definition
- ADR-0001 — graph database selection and GraphRAG architecture
- ADR-0004 — parse output contract (scalar flattening amendment)

---

## Amendment — 2026-04-26 — Army-list knowledge extraction

### New node labels

| Label | Source | Key properties |
|---|---|---|
| `:Upgrade` | `data/parsed/upgrades.json` | `upgrade_type`, `points_cost`, `cost_unit`, `points_budget`, `mutex_group`, `applies_to_profile`, `availability_constraint`, `replaces_weapon_id`, `bsb_unlimited_magic_standard`, `order` |
| `:CompositionList` | `data/parsed/composition_lists.json` | `army_id` |
| `:CompositionSlot` | `data/parsed/composition_slots.json` | `army_id`, `slot_name`, `min_pct`, `max_pct`, `composition_list_id` |

`:Upgrade` nodes are **not embedded** independently.  Their names and costs
are included in their parent unit's embedding text under an "Upgrades:" segment.

`:CompositionList` and `:CompositionSlot` are structural scaffolding for army
composition rules; they are not embedded.

### New edge families

| Edge type | Src | Dst | Properties | Source |
|---|---|---|---|---|
| `HAS_UPGRADE` | `:Unit` | `:Upgrade` | — | parsed (`upgrades.json`) |
| `UNLOCKS_RULE` | `:Upgrade` | `:SpecialRule` | — | parsed, classified at coordinator pass |
| `UNLOCKS_WEAPON` | `:Upgrade` | `:Weapon` | — | relabeled from `UNLOCKS_RULE` in coordinator two-pass |
| `UNLOCKS_ITEM` | `:Upgrade` | `:MagicItem` | — | relabeled from `UNLOCKS_RULE` in coordinator two-pass |
| `UNLOCKS_MOUNT` | `:Upgrade` | `:Unit` | — | parsed (armyListEntry links) |
| `REPLACES_WEAPON` | `:Upgrade` | `:Weapon` | — | parsed (weapon swap items) |
| `HAS_LIST` | `:Army` | `:CompositionList` | — | parsed |
| `HAS_SLOT` | `:CompositionList` | `:CompositionSlot` | — | parsed |
| `SLOT_ALLOWS` | `:CompositionSlot` | `:Unit` | `max_count`, `per_points` | parsed |
| `ALLIED_WITH` | `:Army` | `:Army` | `alliance_type` | parsed |
| `CAN_TAKE_ITEM` | `:Unit` | `:MagicItem` | `budget`, `via_upgrade` | **derived** (post-load Cypher) |

### Derived CAN_TAKE_ITEM policy

`CAN_TAKE_ITEM` edges are not stored in `edges.json`.  They are materialised
by `GraphBuilder._derive_can_take_item()` after all nodes and edges are loaded,
using three idempotent MERGE passes:

1. **magic_item_budget / command_bsb** — unit → all common/army-specific items
   that are not `magic_standard` or `ability`, respecting `wizard_level >= 1`
   for `arcane_item` access.
2. **magic_standard_budget** — unit → `magic_standard` items in the same army
   (or with `army_id IS NULL`).
3. **vampiric_powers_budget / rune_budget** — unit → `ability` items belonging
   to the same army.

Edge properties: `r.budget` (integer, from `up.points_budget`) and
`r.via_upgrade` (the upgrade node id that triggered creation).

**Boundary:** prose-level restrictions ("may not take items from the same
category more than once") are not enforced at the graph level.  They remain in
`:MagicItem.text`.  The graph models structural eligibility only; fine-grained
validation is the responsibility of the application layer.

### Coordinator two-pass edge classifier

The parse coordinator (`pipeline/scraper/parsers/__init__.py`) runs two passes
after all parsers complete:

- **Pass 1:** `UNLOCKS_RULE` edges whose `dst` id matches a known weapon slug
  are relabeled `UNLOCKS_WEAPON`; those matching a magic item slug become
  `UNLOCKS_ITEM`.
- **Pass 2:** `rule_add` upgrade nodes that have at least one `UNLOCKS_WEAPON`
  or `UNLOCKS_MOUNT` edge are promoted to `weapon_add`.
