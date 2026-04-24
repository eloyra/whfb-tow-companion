# Graph Builder + Embeddings — Execution Plan

*Refines `docs/plans/graph-builder-implementation.md` (commit 046e32d) with nested-property handling, profile-as-node, graph-context embeddings, and ADR-0004 amendment. Only deltas and concrete tasks here — the parent plan still applies for everything not contradicted below. Drafted 2026-04-24.*

## Context

Scrape and parse stages are done. `data/parsed/` holds 13 JSON files, 4,716 nodes, 12,170 edges. Next stage: load into Neo4j + generate embeddings so the GraphRAG backend (ADR-0001) has a retrieval substrate.

The parent plan assumed parsed records drop straight into `SET n += row`. They do not: `source_citation`, `base_size_mm`, `unit_size`, `profiles`, `i18n` are maps or lists-of-maps, which Neo4j rejects as node properties. Fixing this well also means fixing the embedding strategy (schema-L930 concat is weak for Unit queries like "fast cavalry with high attacks") and the profile model (a JSON-blob `profiles` field kills stat-compare Cypher, the central RAG-vs-graph thesis demo).

Goal: land a load-ready, queryable graph + dense, graph-derived embeddings — without re-litigating closed ADR decisions.

## Binding decisions (confirmed with user)

1. **All scalar/nested-to-scalar transforms happen at parse time.** Loader stays pure MERGE, per ADR-0004.
2. **Profiles as first-class nodes at parse time** — new `:Profile` label + `HAS_PROFILE` edge with `order` property. Synthetic id `<unit-slug>#<profile-name-slug>`.
3. **i18n → per-language scalar columns** (`name`, `name_es`, `text`, `text_es`, `question`, `question_es`, `answer`, `answer_es`, `corrected_text`, `corrected_text_es`, `original_text`, `original_text_es`). Raw `i18n` dict dropped. Frontend does `coalesce(n.name_es, n.name)`.
4. **Scalar-map flattening** (uniform rule):
   - `source_citation.{book,page}` → `source_citation_book`, `source_citation_page`
   - `base_size_mm.{width,depth}` → `base_width_mm`, `base_depth_mm`
   - `unit_size.{min,max}` → `unit_size_min`, `unit_size_max`
5. **One English vector per node.** Multilingual model handles Spanish via shared embedding space (ADR-0001 L67–72). No `n.embedding_es`.
6. **Embedding text built post-load via Cypher**, pulling neighbor context (rules, weapons, army, profiles) into dense per-node text. Per-label builders live in `pipeline/embeddings/text.py`.
7. **Integration test** uses testcontainers-python with `pytest.mark.skip` fallback.
8. **ADR-0005** written as part of this work (Docker + per-label vector indexes + nested-property encoding + profile-as-node).

---

## Progress tracker

### Step A — Parser refactor (parse-time transforms)

- [x] Create `pipeline/scraper/parsers/_flatten.py` with `flatten_source_citation`, `flatten_i18n`, `slugify`
- [x] Modify `ArmyParser` — call flatten helpers; `translatable_fields=["name"]`
- [x] Modify `UnitParser` — flatten source_citation / base_size_mm / unit_size / i18n; pop `profiles` and emit `node_type=profile` records + `HAS_PROFILE` edges with `order` property
- [x] Modify `RuleParser` (SpecialRule) — flatten helpers; `["name","text"]`
- [x] Modify `CoreRuleParser` — flatten helpers; `["name","text"]`
- [x] Modify `TroopTypeParser` — flatten helpers; `["name","text"]`
- [x] Modify `WeaponParser` — flatten helpers; `["name","text"]`
- [x] Modify `MagicItemParser` — flatten helpers; `["name","text"]`
- [x] Modify `SpellParser` — flatten helpers; `["name","text"]` (Lore records too)
- [x] Modify `FAQParser` — flatten helpers; `["name","question","answer"]`
- [x] Modify `ErrataParser` — flatten helpers; `["name","original_text","corrected_text"]`
- [x] Modify `pipeline/scraper/parsers/__init__.py` coordinator — route `node_type=profile` → `profiles.json`
- [x] Re-run `make parse` — regenerate `data/parsed/` including new `profiles.json`
- [x] Spot-check: `data/parsed/units.json` contains no nested maps; `profiles.json` exists (945 records); `edges.json` contains `HAS_PROFILE` entries

### Step B — Docker + env + Makefile

- [x] Create `docker/docker-compose.yml` (`neo4j:5.24-community`, APOC plugin, healthcheck, named volumes `neo4j_data` + `neo4j_logs`)
- [x] Add Makefile targets: `neo4j-up`, `neo4j-down`, `neo4j-reset`, `neo4j-logs`
- [x] Extend `.env.example`: `NEO4J_DATABASE`, `EMBEDDING_DIM`, `EMBEDDING_BATCH_SIZE`, `EMBEDDING_DEVICE`, `VECTOR_INDEX_SIMILARITY`, `GRAPH_WIPE_ON_BUILD`
- [ ] Local `.env` populated (NEO4J_PASSWORD not `changeme`)
- [ ] Verify Neo4j responds at http://localhost:7474 after `make neo4j-up`

### Step C — Client, DDL, loader

- [x] Create `pipeline/graph/client.py` — env-driven lazy-singleton driver, `verify_connectivity()`, actionable error on failure ("run `make neo4j-up`"), tenacity retry on transient errors
- [x] Create `pipeline/graph/ddl.py` — `apply_constraints_and_indexes(driver)`: 15 uniqueness constraints (14 schema L719 + `:Profile`) + 7 btree indexes (schema L735) + `:Profile` btree on `order` and `name`, all `IF NOT EXISTS`
- [x] Create `pipeline/graph/loader.py` — `load_nodes(driver, label, records, batch_size=500)` (UNWIND MERGE + `SET n += row`); `load_edges(driver, records, batch_size=500)` grouped per-relation with `apoc.merge.relationship(s, row.relation, {}, row.properties, d)` and MATCH (not MERGE) on endpoints

### Step D — Builder, seeds, validator

- [x] Create `pipeline/graph/seeds.py` — copy `ALLIANCE_SEED` (schema L786) and `TERRAIN_INTERACTION_SEED` (schema L814) verbatim; two `seed_*` functions using MERGE; silent-skip when endpoints missing
- [x] Fill `pipeline/graph/builder.py` stub — `GraphBuilder.build()` orchestrator per Step D pseudocode in this plan
- [x] Fill `pipeline/graph/validator.py` stub — counts per label/relation, orphan edge categorisation, dangling `troop_type_id`, PART_OF_SECTION-drop informational report, sanity threshold >5% raises
- [x] Write `data/graph/load_report.json` on every build (validator writes it)
- [ ] First successful `make build-graph` after `make neo4j-reset && make neo4j-up`

### Step E — Embeddings

- [x] Create `pipeline/embeddings/text.py` — per-label graph-context builders (see table below)
- [x] Fill `pipeline/embeddings/generator.py` — SentenceTransformer once, streaming batches with `WHERE n.embedding IS NULL` (resumable), `UNWIND` write-back, final call to `vector_store.create_vector_indexes`
- [x] Fill `pipeline/embeddings/vector_store.py` — one `CREATE VECTOR INDEX … IF NOT EXISTS` per embeddable label, dim 768, cosine
- [ ] First successful `make embed`
- [ ] Verify resumable: rerun `make embed` processes zero nodes
- [ ] Verify round-trip `db.index.vector.queryNodes` returns sensible neighbors for a sample query

### Step F — Pipeline wiring + constants

- [x] Uncomment imports in `pipeline/run_pipeline.py` L37–44 (`GraphBuilder`, `EmbeddingGenerator`)
- [x] Extend `pipeline/constants.py`: `EdgeType.HAS_PROFILE`, `NodeType.PROFILE`, `NODE_TYPE_TO_LABEL`, `EMBEDDABLE_LABELS`, `EMBEDDING_DIM=768`, `VECTOR_INDEX_SIMILARITY="cosine"`
- [x] Add `testcontainers[neo4j]>=4.0` to `[project.optional-dependencies].dev` in `pyproject.toml`
- [ ] Confirm `make pipeline` runs scrape → parse → graph → embed → translate cleanly

### Step G — ADRs + tests

- [x] Amend `docs/decisions/ADR-0004-parse-output-contract.md` — add "Parse-time normalisation for graph-safe shapes" section (scalar flattening, i18n per-lang, profiles.json + HAS_PROFILE)
- [x] Create `docs/decisions/ADR-0005-graph-storage-conventions.md` — Docker, per-label vector indexes, profile-as-node rationale, i18n per-lang-column rationale, graph-context embedding text rationale
- [x] Create `tests/unit/test_parser_flattening.py` — fixture record → expected flattened output + extracted profile records + HAS_PROFILE edges
- [x] Create `tests/unit/test_embedding_text.py` — per-label builder concatenation assertions with a fake driver
- [x] Create `tests/integration/test_graph_build.py` — testcontainers Neo4j (skip if unavailable); tiny synthetic dataset; assert counts + idempotency
- [x] `make lint && make test-unit` green (47 tests pass)

---

## Architecture delta

```
pipeline/
  scraper/parsers/
    unit_parser.py          ← modified: emit :Profile + HAS_PROFILE; flatten scalar maps
    _flatten.py (new)       ← flatten_source_citation, flatten_i18n, slugify
    <all other parsers>     ← call flatten helpers
    __init__.py             ← route profiles.json
  graph/
    client.py (new)
    ddl.py (new)
    loader.py (new)
    seeds.py (new)
    builder.py              ← was # TODO
    validator.py            ← was # TODO
  embeddings/
    text.py (new)
    generator.py            ← was # TODO
    vector_store.py         ← was # TODO
  constants.py              ← extensions above
  run_pipeline.py           ← uncomment imports
docker/
  docker-compose.yml (new)
Makefile                    ← neo4j-* targets
.env.example                ← new vars
docs/decisions/ADR-0004-*   ← amended
docs/decisions/ADR-0005-*   ← new
tests/
  unit/test_parser_flattening.py (new)
  unit/test_embedding_text.py (new)
  integration/test_graph_build.py (new)
```

## Step A — parser-level details

`_flatten.py` sketch:

```python
def flatten_source_citation(d: dict) -> dict:
    sc = d.pop("source_citation", None) or {}
    return {
        "source_citation_book": sc.get("book"),
        "source_citation_page": sc.get("page"),
    }

def flatten_i18n(d: dict, translatable_fields: list[str]) -> dict:
    """Lift i18n[lang][field] → `{field}_{lang}`. English already top-level. Drops i18n."""
    i18n = d.pop("i18n", {}) or {}
    out = {}
    for lang, fields in i18n.items():
        if lang == "en":
            continue
        for f in translatable_fields:
            v = fields.get(f)
            if v:
                out[f"{f}_{lang}"] = v
    return out

def slugify(s: str) -> str: ...   # "Blood Knight" → "blood-knight"
```

`UnitParser` emits, in addition to the (flattened) unit record:

```python
# one profile record per entry in the parsed profiles list
{
  "node_type": "profile",
  "id": f"{unit.id}#{slugify(profile['name'])}",
  "url": unit.url,
  "name": profile["name"],
  "M": profile.get("M"), "WS": profile.get("WS"), "BS": profile.get("BS"),
  "S":  profile.get("S"),  "T":  profile.get("T"),  "W":  profile.get("W"),
  "I":  profile.get("I"),  "A":  profile.get("A"),  "Ld": profile.get("Ld"),
  "order": index,
  "source_citation_book": unit_sc_book,
  "source_citation_page": unit_sc_page,
}
# and one edge
{"src": unit.id, "dst": profile_id, "relation": "HAS_PROFILE", "properties": {"order": index}}
```

## Step C — loader shapes

```python
def load_nodes(driver, label: str, records: list[dict], batch_size: int = 500) -> int:
    # UNWIND $rows AS row MERGE (n:<Label> {id: row.id}) SET n += row
    # nested structures already gone → SET n += row is safe

def load_edges(driver, records: list[dict], batch_size: int = 500) -> dict[str, int]:
    # group by row.relation; per-relation query:
    """
      UNWIND $rows AS row
      MATCH (s {id: row.src}) MATCH (d {id: row.dst})
      CALL apoc.merge.relationship(s, row.relation, {}, row.properties, d) YIELD rel
      RETURN count(rel)
    """
    # MATCH (not MERGE) on endpoints → missing endpoint silently drops; counts per relation
```

## Step D — builder order

1. `client.get_driver()`
2. If `GRAPH_WIPE_ON_BUILD=true`: `MATCH (n) DETACH DELETE n` + drop constraints/indexes
3. `ddl.apply_constraints_and_indexes(driver)`
4. Seed TroopType attrs from `TROOP_TYPE_SEED` (dict-keyed by slug)
5. Load node files (order for log clarity): `armies, troop_types, units, profiles, special_rules, core_rules, documents, lores, spells, weapons, magic_items, faqs, errata`
6. `loader.load_edges(driver, edges.json)`
7. `seeds.seed_alliances`, `seeds.seed_terrain_interactions`
8. `validator.run_all`
9. Write `data/graph/load_report.json`; log per-label / per-relation counts, drops, duration

## Step D — validator

- Node counts per label vs expected JSON counts.
- Edge counts per relation vs `edges.json`.
- Orphan edges: per-relation src/dst that failed to match, categorised missing-src vs missing-dst.
- **PART_OF_SECTION expected-drop**: parsed data includes ~1,514 edges whose `dst` is a URL-prefix slug never scraped as a node. Treat as informational, not error. (Correcting earlier doc claim of "76 drops" — 76 is the successfully-loaded count, not the drop count.)
- Dangling `troop_type_id`: `MATCH (u:Unit) WHERE u.troop_type_id IS NOT NULL AND NOT EXISTS { MATCH (t:TroopType {id: u.troop_type_id}) }`.
- Writes `data/graph/load_report.json`.
- Sanity threshold: >5% unexpected drops for any relation other than PART_OF_SECTION → raise.

## Step E — embedding text per label

| Label | Text composition |
|---|---|
| `:Unit` | `"{name}. {army_name}. {troop_type_name}. {army_category}. {cost_points_per_model} pts/model. Unit size {min}-{max}. Base {W}x{D}mm. Profiles — {name}: {stat block}; …. Rules: {rule_names}. Weapons: {weapon_names}."` |
| `:SpecialRule` | `"{name}. {text}"` |
| `:CoreRule` | `"{name}. {text}"` |
| `:Document` | `"{name}. {text}"` |
| `:TroopType` | `"{name}. {category}. Rank bonus min {min_models} / max +{max_rank}. Strength {unit_strength_per_model}. {text}"` |
| `:Spell` | `"{name}. Lore of {lore_name}. {text}"` |
| `:MagicItem` | `"{name}. {item_type}. {points_cost} pts. {text}"` |
| `:Lore` | `"{name}. {text}. Spells: {spell_names}."` |
| `:Weapon` | `"{name}. {weapon_class}. Range {range} Str {strength} AP {ap}. Special rules: {special_rules_csv}. {text}"` |
| `:FAQ` | `"{question} {answer}"` |
| `:Errata` | `"{original_text} → {corrected_text}"` |
| `:Army` | `"{name}"` (short — multilingual model embeds names well) |
| `:Profile` | **Not embedded** — addressable via parent Unit, which serialises it inside the Unit's text. |

## Step E — vector index DDL (per label)

```cypher
CREATE VECTOR INDEX <snake_label>_embedding_idx IF NOT EXISTS
FOR (n:<Label>) ON (n.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 768,
  `vector.similarity_function`: 'cosine'
}}
```

Rationale: per-label indexes give cheaper label-scoped queries from `VectorCypherRetriever` (ADR-0001); Neo4j 5.x vector indexes are per-label-per-property.

---

## Verification

1. **Parse regression**
   - `make parse` completes.
   - `data/parsed/profiles.json` exists; record count = sum of `len(unit.profiles)` across parsed Unit HTMLs.
   - `data/parsed/edges.json` gains `HAS_PROFILE` entries equal to the profile count.
   - No `data/parsed/*.json` file contains nested `i18n`, `source_citation`, `base_size_mm`, `unit_size`, or `profiles` fields on node records.
2. **Fresh graph build**
   - `make neo4j-reset && make neo4j-up` (wait for healthcheck); http://localhost:7474 responds.
   - `make build-graph`: `data/graph/load_report.json` shows zero missing-src drops, ~1,514 PART_OF_SECTION missing-dst drops (documented), per-label counts match JSON input.
3. **Cypher spot-checks**
   ```cypher
   MATCH (u:Unit)-[:HAS_PROFILE]->(p:Profile) WHERE p.WS >= 5 AND p.S >= 5
   RETURN u.name, p.name, p.WS, p.S ORDER BY u.name LIMIT 10;

   MATCH (u:Unit {id:"blood-knights"})-[:HAS_RULE]->(r:SpecialRule) RETURN r.name ORDER BY r.name;

   MATCH (u:Unit {id:"blood-knights"})
   RETURN u.source_citation_book, u.source_citation_page,
          u.base_width_mm, u.base_depth_mm, u.unit_size_min, u.unit_size_max;
   ```
4. **Embedding**
   - `make embed`: progress bar advances per label; re-run processes zero nodes (resumable via `WHERE n.embedding IS NULL`).
   - `SHOW VECTOR INDEXES` lists one per embeddable label.
   - Round-trip query:
     ```cypher
     CALL db.index.vector.queryNodes('special_rule_embedding_idx', 3, $embedding) YIELD node, score
     RETURN node.name, score;
     ```
5. **Idempotency** — rerun `make build-graph` → `load_report.json` zero new nodes / zero new edges.
6. **Persistence** — `make neo4j-down && make neo4j-up` — data survives (volume intact).
7. **Quality gates** — `make lint && make test-unit` pass; integration test passes or skips cleanly.

---

## Critical files (modify / create)

**Modify**
- `pipeline/scraper/parsers/unit_parser.py`
- `pipeline/scraper/parsers/{army,rule,core_rule,troop_type,weapon,magic_item,spell,faq,errata}_parser.py`
- `pipeline/scraper/parsers/__init__.py`
- `pipeline/graph/builder.py`, `pipeline/graph/validator.py`
- `pipeline/embeddings/generator.py`, `pipeline/embeddings/vector_store.py`
- `pipeline/run_pipeline.py` L37–44
- `pipeline/constants.py`
- `Makefile`
- `.env.example`
- `pyproject.toml`
- `docs/decisions/ADR-0004-parse-output-contract.md`

**Create**
- `pipeline/scraper/parsers/_flatten.py`
- `pipeline/graph/{client,ddl,loader,seeds}.py`
- `pipeline/embeddings/text.py`
- `docker/docker-compose.yml`
- `docs/decisions/ADR-0005-graph-storage-conventions.md`
- `tests/unit/test_parser_flattening.py`
- `tests/unit/test_embedding_text.py`
- `tests/integration/test_graph_build.py`

**Not changing**
- `data/parsed/*.json` contract — amended (new file + flattened shape), no schema-incompatible rewrites.
- Edge-list structure.
- ADR-0001.

## Reused utilities

- `pipeline.constants.TROOP_TYPE_SEED` (dict-keyed by slug).
- `pipeline.constants.CHARACTERISTIC_MAP`.
- `pipeline.constants.NodeType`, `EdgeType` — extend with `PROFILE`, `HAS_PROFILE`.
- Schema seed templates (`ALLIANCE_SEED`, `TERRAIN_INTERACTION_SEED`).
- `python-dotenv` loader pattern from `backend/llm/client.py` L11.
- `tenacity` — retry on Neo4j transient errors in `client.get_driver()`.

## Out of scope

- Translations stage (`make translate`) — separate; fills `name_es`, `text_es`, etc.
- `:Terrain` / `:Upgrade` ingest — parsers don't emit them; DDL creates constraints so later ingest is pure data.
- `APPLIES_TO` FAQ/Errata enrichment — fuzzy matching; deferred.
- PART_OF_SECTION targets → real `:Section` nodes — schema amendment; deferred.
- `Weapon → SpecialRule` derived edges from `weapon.special_rules` — deferred.
- Embedding `:Profile` directly — redundant; parent Unit's embedding already contains the stat block.

## Resume checklist

- [ ] Re-read this file + `docs/plans/graph-builder-implementation.md` + ADR-0001 + ADR-0004 + `docs/schema/knowledge_graph_schema.md` L700–945.
- [ ] Confirm `.env` has real `NEO4J_PASSWORD`.
- [ ] Work top-to-bottom through the Progress tracker. Tick boxes as steps land.
