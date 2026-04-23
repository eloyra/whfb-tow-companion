# Neo4j Graph Builder + Embeddings Implementation Plan

*Drafted 2026-04-23. Tracks the next pipeline milestone after scrape + parse.*

## Context

Scrape and parse stages are done. `data/parsed/` holds 13 JSON files (12 node files + `edges.json`, 15,213 edges). Next pipeline stage: load this into Neo4j and generate embeddings in-place. The resulting graph is the retrieval substrate for the GraphRAG backend (ADR-0001).

Hard constraints from ADRs/schema:
- **Neo4j Community Edition 5.11+** (native HNSW vector index) via Docker, APOC plugin, persisted volume (ADR-0001).
- Embeddings generated in Python with `sentence-transformers` (`paraphrase-multilingual-mpnet-base-v2`, 768 dim), written to `n.embedding`, indexed after write. **No** `genai.vector.encode()` (ADR-0001 L67–72).
- Parse-output contract (ADR-0004): node-type-per-file + shared `edges.json`, slugs as `id`, MERGE-on-id idempotency.
- Node records already match schema v3.0 — builder is a pure loader, no transforms beyond nulls/enums.

## Architecture

Three new packages, everything else already scaffolded:

```
pipeline/graph/
  client.py        # Neo4j driver factory (lazy singleton, env-driven)
  ddl.py           # Constraints + btree + vector-index DDL, idempotent
  loader.py        # Node + edge loader (MERGE-based, batched, UNWIND)
  builder.py       # GraphBuilder orchestrator (was a stub)
  validator.py     # Post-load integrity checks (was a stub)
  seeds.py         # ALLIANCE_SEED + TERRAIN_INTERACTION_SEED application
pipeline/embeddings/
  text.py          # text_for_embedding(node, lang) — mirrors schema L930
  generator.py     # EmbeddingGenerator orchestrator (was a stub)
  vector_store.py  # Vector-index creation + bulk SET n.embedding (was a stub)
docker/
  docker-compose.yml   # Neo4j 5.x-community + apoc + named volume
```

## Docker: portable Neo4j

Create `docker/docker-compose.yml`. Minimal service; credentials from `.env`. Persistence via named volume so `docker compose down` keeps data.

```yaml
services:
  neo4j:
    image: neo4j:5.24-community            # pinned; must be >=5.11 for native HNSW
    container_name: whfb-neo4j
    ports:
      - "7474:7474"                        # Browser UI
      - "7687:7687"                        # Bolt
    environment:
      NEO4J_AUTH: ${NEO4J_USER}/${NEO4J_PASSWORD}
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_server_memory_heap_initial__size: 512m
      NEO4J_server_memory_heap_max__size: 1G
      NEO4J_server_memory_pagecache_size: 512m
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:7474 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10
volumes:
  neo4j_data:
  neo4j_logs:
```

Add Makefile targets (below `install:`):
- `neo4j-up` → `docker compose -f docker/docker-compose.yml up -d` then wait for healthcheck.
- `neo4j-down` → `docker compose -f docker/docker-compose.yml down` (keeps volume).
- `neo4j-reset` → `docker compose -f docker/docker-compose.yml down -v` (wipes volume — destructive, documented).
- `neo4j-logs` → tails container logs.

`.env.example` additions:
```
NEO4J_DATABASE=neo4j
EMBEDDING_DIM=768
EMBEDDING_BATCH_SIZE=64
EMBEDDING_DEVICE=cpu                # cpu | cuda | mps
VECTOR_INDEX_SIMILARITY=cosine
GRAPH_WIPE_ON_BUILD=false           # true for clean rebuild
```

## Builder (`pipeline/graph/builder.py`)

`GraphBuilder.build()` orchestration, ordered:

1. **Connect** via `pipeline.graph.client.get_driver()` — verifies connectivity with `driver.verify_connectivity()`; raises on failure with actionable message ("run `make neo4j-up`").
2. **Optional wipe**: if `GRAPH_WIPE_ON_BUILD=true`, `MATCH (n) DETACH DELETE n` + drop all indexes/constraints. Otherwise skip (idempotent MERGE path).
3. **Apply DDL** (`ddl.apply_constraints_and_indexes(driver)`): runs the 14 uniqueness constraints + 7 btree indexes from `docs/schema/knowledge_graph_schema.md` L719–741, all `IF NOT EXISTS`.
4. **Seed `TroopType`** from `pipeline/constants.py TROOP_TYPE_SEED` — MERGE-on-id so rank/strength attrs exist even when explainer TroopType pages carry nulls.
5. **Load node files** in fixed order (order doesn't matter for MERGE, but this ordering keeps log output readable):
   `armies.json`, `troop_types.json`, `units.json`, `special_rules.json`, `core_rules.json`, `documents.json`, `lores.json`, `spells.json`, `weapons.json`, `magic_items.json`, `faqs.json`, `errata.json`.
   Each file → `loader.load_nodes(driver, label, records)` using batched `UNWIND $rows AS row MERGE (n:<Label> {id: row.id}) SET n += row`. Batch size 500.
6. **Load edges** from `edges.json` via `loader.load_edges(driver, records)` — groups by relation type, batches with `UNWIND`, runs `MATCH ... MATCH ... MERGE` (never plain CREATE — avoids accidental node creation on typos). Relation-type string passed via `apoc.create.relationship` / `apoc.merge.relationship` to allow a dynamic type in a single query. `properties` is an empty-dict passthrough (parser contract L55–67 of ADR-0004).
7. **Apply seeds** (`seeds.seed_alliances`, `seeds.seed_terrain_interactions`) — both are no-op-safe when seed tables are empty. Schema-provided seed templates in `docs/schema/knowledge_graph_schema.md` L786–842 go into `pipeline/graph/seeds.py` as `ALLIANCE_SEED = [...]` and `TERRAIN_INTERACTION_SEED = [...]` constants. Populate with the partial data already documented in the schema; expanding is a separate tracking task, not a blocker.
8. **Validate** (`validator.run_all`) — see Validator section.
9. **Log summary**: counts per label + per relation, orphan count, duration.

### Handling known data-shape quirks

- **PART_OF_SECTION orphan targets** (76 edges pointing to free-text section slugs like `"magic"` that are not nodes): loader's `MATCH ... MATCH ... MERGE` pattern silently skips any edge whose endpoints don't exist. `validator` counts and reports these. Decision: **drop silently at load time, surface in validator output**, document as deferred. A follow-up task will introduce a `:Section` label or rewrite these edges to proper CoreRule targets.
- **Name-derived rule slugs** in HAS_RULE edges (parser fallback): today all resolve. Validator will flag any that don't rather than auto-creating stubs.
- **TroopType explainer rows** (19/40 with `category: "unknown"`): loaded as-is — their fields are already nullable per schema.
- **Weapon.special_rules is plain-text names, not slugs**: stored verbatim on the node. No derived edges. If future work wants `Weapon-[:HAS_RULE]->SpecialRule`, it goes in a post-load enrichment step, not the builder.
- **Schema vs implemented gap**: `:Terrain`, `:Upgrade`, `ALLIED_WITH`, `TERRAIN_INTERACTION` are in the schema but have no parsed data yet. Builder creates constraints/indexes for them so later ingest doesn't need migrations, and seeds apply whatever partial static data the schema provides.

## Loader (`pipeline/graph/loader.py`)

Two core functions. All writes batched, all idempotent.

```python
def load_nodes(driver, label: str, records: list[dict], batch_size: int = 500) -> int:
    query = f"""
        UNWIND $rows AS row
        MERGE (n:{label} {{id: row.id}})
        SET n += row
    """
    # chunked executeWrite; returns count
```

```python
def load_edges(driver, records: list[dict], batch_size: int = 500) -> dict[str, int]:
    # Group by relation, iterate:
    query = """
        UNWIND $rows AS row
        MATCH (s {id: row.src})
        MATCH (d {id: row.dst})
        CALL apoc.merge.relationship(s, row.relation, {}, row.properties, d)
        YIELD rel
        RETURN count(rel)
    """
```

`MATCH` (not `MERGE`) on endpoints is deliberate: missing endpoint → no edge created → loader counts the miss and returns per-relation drop counts. Label is inferred from `id` via a pre-built in-Python slug→label dict (built during node load) so `MATCH` can be labeled for speed; fallback to unlabeled `MATCH` when label unknown (cheaper than per-row lookup given the scale).

Use `apoc.merge.relationship(startNode, relType, identProps, onMatchProps, endNode)` with `identProps={}` so relationships are deduplicated by (start, type, end) — re-runs without `GRAPH_WIPE_ON_BUILD` stay idempotent.

## DDL (`pipeline/graph/ddl.py`)

One Python function `apply_constraints_and_indexes(driver)` runs every `CREATE CONSTRAINT` and `CREATE INDEX` from schema L719–741, all guarded with `IF NOT EXISTS`. Idempotent.

Add constraints for `:Document` (present in schema) and ensure all 14 labels are covered.

Vector-index creation lives in `pipeline/embeddings/vector_store.py` (separate stage — runs after embeddings exist; Neo4j requires ≥1 node with a vector property before index is useful).

## Validator (`pipeline/graph/validator.py`)

`validator.run_all(driver) -> dict`:
- Count nodes per label; compare to expected JSON record counts.
- Count edges per relation; compare to `edges.json`.
- **Orphan edges**: expected edges in `edges.json` that failed to load (missing endpoint). Report src/dst/relation for each, categorised by missing-src vs missing-dst.
- **Dangling `troop_type_id`**: `MATCH (u:Unit) WHERE u.troop_type_id IS NOT NULL AND NOT EXISTS { MATCH (t:TroopType {id: u.troop_type_id}) } RETURN count(u)`.
- **PART_OF_SECTION** endpoint health (expected to report ~76 drops — document, don't fail).
- **Writes a report** to `data/graph/load_report.json` with counts, drops, and durations. Non-zero drops are warnings, not errors, unless a sanity threshold is exceeded (>5% of a relation type missing → raise).

## Embeddings stage (`pipeline/embeddings/`)

Separate stage (`make embed`). Runs after graph build. Two-phase: write vectors, then build index.

### `text.py`

`text_for_embedding(node_data: dict, lang: str = "en") -> str` — direct port of schema L930–940. Concatenates `text`, `question`, `answer`, `name` in that order, preferring `i18n[lang]` then top-level. Returns `""` when node has no text-bearing fields (Army, Upgrade) — caller decides whether to skip or embed the name alone.

### `generator.py`

`EmbeddingGenerator.run()`:
1. Load model once: `SentenceTransformer(EMBEDDING_MODEL, device=EMBEDDING_DEVICE)`.
2. For each embeddable label (see table below), stream nodes from Neo4j in batches: `MATCH (n:<Label>) WHERE n.embedding IS NULL RETURN n.id AS id, n { .* } AS props`. `WHERE n.embedding IS NULL` makes the stage resumable — re-running skips already-embedded nodes.
3. Build `[text_for_embedding(props) for props in batch]`, filter out empty strings, call `model.encode(texts, batch_size=EMBEDDING_BATCH_SIZE, show_progress_bar=True, convert_to_numpy=True)`.
4. Write back with `UNWIND $rows AS row MATCH (n:<Label> {id: row.id}) SET n.embedding = row.embedding` — list of floats, batched 200.
5. Final step: call `vector_store.create_vector_indexes(driver)`.

Embeddable labels and the text used:

| Label | Text fields (in order) | Notes |
|---|---|---|
| `:SpecialRule` | text, name | |
| `:CoreRule` | text, name | |
| `:Document` | text, name | |
| `:TroopType` | text, name | Skip category=`unknown` explainer rows (will have empty text anyway) |
| `:Spell` | text, name | |
| `:MagicItem` | text, name | |
| `:Lore` | text, name | |
| `:FAQ` | question, answer, name | |
| `:Errata` | corrected_text, original_text, name | |
| `:Weapon` | text, name | Skip rows with empty text+stats |
| `:Unit` | name + profiles-summary | No free `text`; build synthetic summary from name, troop_type_id, profiles (stat block serialised) |
| `:Army` | name | Short; still useful for query-side "Vampire Counts" matches |

Unit synthetic summary example: `"Blood Knights, Heavy Cavalry. Profiles: Blood Knight WS5 BS3 S4 T4 W1 I4 A2 Ld7; Kastellan WS5 BS3 S4 T4 W1 I4 A3 Ld7; Nightmare M7 WS3 S4 I2 A1."` Keeps the vector meaningful for queries like "fast cavalry with high attacks".

### `vector_store.py`

`create_vector_indexes(driver, dim: int = 768, similarity: str = "cosine")`:

One vector index per embeddable label, named `<label>_embedding_idx`. Example:

```cypher
CREATE VECTOR INDEX special_rule_embedding_idx IF NOT EXISTS
FOR (n:SpecialRule) ON (n.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 768,
  `vector.similarity_function`: 'cosine'
}}
```

Rationale for per-label (not a shared multi-label) index: Neo4j 5.x vector indexes are per-label per-property, and per-label indexes give the retriever cheaper label-scoped queries from the `VectorCypherRetriever` (ADR-0001). Cosine matches `sentence-transformers` default and is what `paraphrase-multilingual-mpnet-base-v2` is trained for.

## Integration points

- `pipeline/run_pipeline.py` L37–44: uncomment the TODO imports. `run_graph()` → `GraphBuilder().build()`; `run_embed()` → `EmbeddingGenerator().run()`. Running `--all` executes scrape → parse → graph → embed → translate in order, which is the desired sequence.
- `pipeline/constants.py`: add `EMBEDDING_DIM = 768`, `VECTOR_INDEX_SIMILARITY = "cosine"`, a `NODE_TYPE_TO_LABEL: dict[str, str]` map (e.g. `"special_rule" → "SpecialRule"`), and an `EMBEDDABLE_LABELS: dict[str, list[str]]` declaring the text-field order per label.
- `pyproject.toml`: nothing to add — `neo4j`, `neo4j-graphrag`, `sentence-transformers`, `tqdm`, `python-dotenv`, `tenacity` are already declared. APOC must be enabled in Docker (handled by `NEO4J_PLUGINS`).

## Files to modify / create

**Create:**
- `docker/docker-compose.yml`
- `pipeline/graph/client.py`
- `pipeline/graph/ddl.py`
- `pipeline/graph/loader.py`
- `pipeline/graph/seeds.py`
- `pipeline/embeddings/text.py`
- `tests/integration/test_graph_build.py` (end-to-end smoke)

**Modify (fill in stubs):**
- `pipeline/graph/builder.py` (currently `# TODO` only)
- `pipeline/graph/validator.py` (currently `# TODO` only)
- `pipeline/embeddings/generator.py` (currently `# TODO` only)
- `pipeline/embeddings/vector_store.py` (currently `# TODO` only)
- `pipeline/run_pipeline.py` (L37–44, uncomment imports)
- `pipeline/constants.py` (add `EMBEDDING_DIM`, `NODE_TYPE_TO_LABEL`, `EMBEDDABLE_LABELS`)
- `Makefile` (add `neo4j-up`, `neo4j-down`, `neo4j-reset`, `neo4j-logs`)
- `.env.example` (add `NEO4J_DATABASE`, `EMBEDDING_DIM`, `EMBEDDING_BATCH_SIZE`, `EMBEDDING_DEVICE`, `VECTOR_INDEX_SIMILARITY`, `GRAPH_WIPE_ON_BUILD`)
- `docs/decisions/` — add ADR-0005 documenting the Docker setup and the vector-index-per-label decision

**Not changing:**
- `data/parsed/*.json` — contract is fixed.
- Parsers — out of scope.

## Reused utilities

- `pipeline.constants.TROOP_TYPE_SEED` (L34), `CHARACTERISTIC_MAP` (L8), `NodeType` (L145), `EdgeType` (L230), `SUPPORTED_LANGUAGES` (L21).
- Schema seed templates (`ALLIANCE_SEED` at schema L786, `TERRAIN_INTERACTION_SEED` at L814) copied verbatim into `pipeline/graph/seeds.py`.
- `python-dotenv` pattern from `backend/llm/client.py` L11 for env loading.
- `tenacity` (already declared) for retry on Neo4j driver transient errors.

## Verification

1. **Fresh volume smoke test**:
   - `make neo4j-reset && make neo4j-up` — verify Neo4j browser at http://localhost:7474 responds.
   - `make build-graph` — wall-clock; expect load_report.json with zero missing-src drops, ~76 PART_OF_SECTION drops (documented).
   - `make embed` — verify progress bar advances; re-run to confirm `WHERE n.embedding IS NULL` skip path.
2. **Cypher spot-checks** via `cypher-shell` (works via docker exec or browser):
   ```cypher
   // Node counts per label match JSON record counts
   MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c ORDER BY c DESC
   // Schema query from ADR/schema L860
   MATCH (u:Unit {id: "blood-knights"})-[:HAS_RULE]->(r:SpecialRule)
   RETURN r.name ORDER BY r.name
   // Vector index round-trip
   CALL db.index.vector.queryNodes('special_rule_embedding_idx', 3, $embedding)
   ```
3. **Integration test** `tests/integration/test_graph_build.py`:
   - Start ephemeral Neo4j via testcontainers-python if available, else skip with a marker.
   - Load a tiny synthetic parsed dataset (5 nodes, 4 edges) and assert counts + one vector query.
4. **Idempotency**: run `make build-graph` twice without wipe → second run's load_report.json must show zero new nodes and zero new edges (MERGE).
5. **Resumability**: kill `make embed` midway; re-run → confirm only unembedded nodes are processed.
6. **Persistence**: `make neo4j-down && make neo4j-up` — data survives (volume not removed).
7. `make lint && make test-unit` — no new ruff or type violations.

## Out of scope (explicit non-goals for this plan)

- Translations (`make translate`) — handled by a separate stage that fills `i18n.es`; graph builder is language-agnostic.
- `:Terrain` / `:Upgrade` node ingest — parsers don't emit them; schema constraints created so future ingest is a pure data change.
- `APPLIES_TO` edges from FAQ/Errata to referenced rules — requires fuzzy name matching; tracked as a follow-up enrichment pass.
- Converting `PART_OF_SECTION` targets to real `:Section` nodes — needs schema amendment; deferred.
- Weapon→SpecialRule derived edges from `weapon.special_rules` plain-text list — deferred.

## Resume checklist for next session

- [ ] Re-read this file + ADR-0001 + ADR-0004 + `docs/schema/knowledge_graph_schema.md` L700–945.
- [ ] Confirm `.env` has Neo4j password set (not `changeme`).
- [ ] Start with `docker/docker-compose.yml` + Makefile targets + `.env.example` updates.
- [ ] Then `pipeline/graph/client.py` → `ddl.py` → `loader.py` → `builder.py`, in that order.
- [ ] Then embeddings package.
- [ ] Then validator + integration test.
- [ ] Finish with ADR-0005 writeup documenting Docker + per-label vector index choices.
