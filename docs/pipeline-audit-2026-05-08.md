# Pipeline Audit Report — 2026-05-08

Comprehensive audit of the scraping, parsing, and graph building pipeline against
ADRs, the knowledge graph schema v3.0, and realistic Warhammer: The Old World
user queries.

---

## 1. ADR Compliance Summary

| ADR | Title | Compliant? | Notes |
|-----|-------|-----------|-------|
| **ADR-0001** | Neo4j Selection | ✅ Full | Docker `neo4j:5.24-community` + APOC, HNSW vector indexes, `neo4j-graphrag` ready |
| **ADR-0002** | Crawler Architecture | ✅ Full | Dual-seed BFS, ISR fallback detection with retry (3×, 5s delay), 13 URL classifiers in `utils.py`, `robots.txt` respected, User-Agent identifies project |
| **ADR-0003** | Wiki-Only Data | ✅ Full | No cross-page joins needed; `__NEXT_DATA__` JSON extraction covers all data; all parsers operate on `pageProps` without DOM traversal; bridging section of ADR-0004 correctly superseded |
| **ADR-0004** | Parse Output Contract | ✅ Full | 16 flat output files in `data/parsed/`; nested maps flattened to scalars at parse time; profiles emitted as first-class nodes with `HAS_PROFILE` edges; two-pass edge classifier post-parse |
| **ADR-0005** | Storage Conventions | ✅ Core | Per-label vector indexes ✅; parse-time property flattening ✅; profiles as `:Profile` nodes ✅; i18n per-language scalar columns ✅; single English vector per node ✅; CAN_TAKE_ITEM derivation ✅ |
| **ADR-0005 Amend** | Army-list Knowledge | ✅ Mostly | `:Upgrade`/`:CompositionList`/`:CompositionSlot` nodes ✅; two-pass edge relabeling (UNLOCKS_RULE→UNLOCKS_WEAPON/ITEM) ✅; `rule_add`→`weapon_add` promotion ✅; derived `CAN_TAKE_ITEM` ✅. BUT: `:Terrain` nodes not parsed, `SPLIT_PROFILE_OF` not emitted |

---

## 2. Knowledge Graph Schema v3.0 — Compliance Gaps

### GAP 1: `:Terrain` Nodes Not Parsed (HIGH)

The schema defines 14 `:Terrain` nodes with 13 properties each (`terrain_class`,
`blocks_movement`, `disrupts_units`, `requires_dangerous_test`, `grants_cover`,
`movement_penalty`, `special_feature_benefit`). The DDL already includes a
`terrain_id` uniqueness constraint, and `seeds.py` already has a
`TERRAIN_INTERACTION_SEED`.

**What's missing:**

- `NodeType` enum has no `TERRAIN` member
- No `TerrainParser` class exists
- `classify_url()` in `utils.py` has no pattern for `/battlefield-terrain/{slug}`
- Terrain pages (e.g., `/battlefield-terrain/difficult-terrain`) are routed to
  `CoreRuleParser`, which misclassifies them
- `seed_terrain_interactions()` silently writes 0 edges because `MATCH (t:Terrain
  {id: ...})` finds no nodes

**Impact on queries (5 failures):**

- "Can Scouts deploy in woods?"
- "Does Ethereal ignore dangerous terrain?"
- "What terrain disrupts units?"
- "Is cover granted by woods partial or full?"
- "What are the rules for Open Ground?"

**Fix:**
1. Add `TERRAIN = "terrain"` to `NodeType` in `constants.py`
2. Add `"terrain": "Terrain"` to `NODE_TYPE_TO_LABEL`
3. Add a `terrain` URL pattern to `classify_url()` in `utils.py`
4. Create `TerrainParser` that extracts terrain properties from the
   `__NEXT_DATA__` blob on `/battlefield-terrain/{slug}` pages
5. Register `TerrainParser` in the coordinator registry

---

### GAP 2: `SPLIT_PROFILE_OF` Edges Not Emitted (MEDIUM)

The schema defines `SPLIT_PROFILE_OF` for mount→rider sub-unit relationships.
The `UnitParser` emits all profiles (rider, champion, mount) as `:Profile` nodes
connected via `HAS_PROFILE`, but **does not distinguish** which profile is a
mount. There is no `SPLIT_PROFILE_OF` edge anywhere in the codebase.

**Impact on queries:**

- "What's the split profile for a Demigryph Knight?" — can get all profiles but
  can't determine which is rider vs mount
- "Find all units that can ride a Nightmare" — `CAN_MOUNT` edge exists from unit
  → mount unit, but the mount's own profile link to the parent unit is missing

**Fix:**
When `UnitParser` encounters a profile whose name matches a known mount unit
slug (or where the profile has no weapons/rules of its own), emit:
```
(profile_mount) -[:SPLIT_PROFILE_OF]-> (unit_rider)
```

---

### GAP 3: Weapon Structured Profile Fields All `None` (MEDIUM)

`weapon_parser.py` explicitly sets to `None`:
`range`, `strength`, `ap`, `special_rules`, `armour_value`, `shots`,
`template_type`, `is_indirect`, `bounce`.

The comment reads: *"not present in Contentful data model."* The data IS
available in the `bodyIndex` text and the `description` rich-text fields, but is
not extracted into structured properties.

**Impact on queries (4 partials):**

- "What's the armour value of full plate armour?" → text only
- "Does a shield give +1 to armour save?" → text only
- "How do Cannon balls bounce?" → text only, `bounce` field is null
- "What weapons have AP -2 or better?" → unqueryable in Cypher

**Fix:**
A regex-based enrichment pass on the `bodyIndex` or `description` text of weapon
pages to populate structured fields. Key patterns to extract:
- `Range: X"` → `range`
- `Strength: S+N / N` → `strength`
- `Armour Piercing: -N` → `ap`
- `Armour Value: N+` or `+N to save` → `armour_value`
- `Template: blast / large blast / flame template` → `template_type`
- `Shots: N / D3 / 2D6` → `shots`
- `Bounce: yes / D3 / N″` → `bounce`
- `Special Rules:` followed by rule names → `special_rules: [slug, ...]`

Alternatively, the `bodyIndex` field on many weapon pages is a pre-flattened
string that already contains structured stat blocks; a table parser on that field
could be more reliable.

---

### GAP 4: Spell Structured Fields Mostly `None` (MEDIUM)

`spell_parser.py` sets `spell_type`, `duration`, `target`,
`casting_value_boosted` to `None`. Comment: *"not in Contentful data model."*

Only `casting_value`, `range`, and `casting_value_override` are extracted.

**Impact on queries:**

- "Which spells are Magic Missiles?" → can't filter by `spell_type`
- "What spells remain in play?" → can't filter by `duration`
- "What spells target enemy units?" → can't filter by `target`

**Fix:**
For standard lores (Strategy 1), the `description` or `body` rich-text contains
type, duration, and target in predictable patterns. A regex pass similar to the
weapon enrichment could populate these fields. For renegade lores (Strategy 2),
the stat table already has `Type` and `Range` columns that are partially parsed.

---

### GAP 5: `HAS_COMPOSITION_RULE` Edge Not Emitted (LOW)

Schema defines `Army → CoreRule` with `HAS_COMPOSITION_RULE`. This would link an
army to its army-list composition page. Not emitted by any parser.

**Fix:**
In `ArmyListParser`, after processing the page, emit:
```
(army_slug) -[:HAS_COMPOSITION_RULE]-> (list_page_slug_as_corerule)
```

---

### GAP 6: Champion Magic Item Budget Not Captured (MEDIUM)

`_options.py` classifies champion upgrades as `command_champion` but does NOT
set `points_budget` for the champion's own magic item allowance. The
`_derive_can_take_item()` query in `builder.py` only looks for:

```cypher
WHERE up.upgrade_type IN ['magic_item_budget', 'command_bsb']
```

Champions with text like "A Seneschal may take up to 25 points of magic items"
generate a `command_champion` upgrade node and a separate `magic_item_budget`
upgrade. But the `magic_item_budget` node has `applies_to_profile` set — and
`_derive_can_take_item()` does not filter by profile scope, so the budget is
granted to the unit, not the champion sub-profile.

**Impact on queries:**

- "How many points of magic items can my unit champion take?" → the budget
  exists but is not profile-scoped in derivation

**Fix:**
Either:
1. Set `points_budget` directly on `command_champion` upgrades with magic item
   allowance text
2. Or modify `_derive_can_take_item()` to consider `up.applies_to_profile`

---

### GAP 7: Standard Bearer Magic Standard Budget Detection (MEDIUM)

`_options.py` classifies standard bearer lines as `command_standard` but does NOT
extract `magic_standard_budget` from the same text. The `magic_standard_budget`
is only detected as a separate upgrade node via the `_BUDGET_RE` pattern on
separate lines like "may carry a magic standard worth up to 50 points."

When a standard bearer line implicitly carries a magic standard budget (e.g.,
"Upgrade one model to a standard bearer (+6 pts) who may carry a magic standard
worth up to 50 pts" — all in one line), the `_STANDARD_RE` matches first and the
budget sub-pattern is never checked.

**Fix:**
After `_STANDARD_RE` match, run `_MAGIC_STANDARD_BUDGET_RE` and `_BUDGET_RE` on
the same text and set `magic_standard_budget` on the command_standard upgrade
node if found.

---

### GAP 8: Inventory of Missing Edge Families

The following edge types exist in the schema but are partially or not
implemented:

| Edge Type | Status | Notes |
|-----------|--------|-------|
| `TERRAIN_INTERACTION` | ⚠️ Seed only | Seed writes 0 edges without `:Terrain` nodes. No dynamic extraction from rule text. |
| `SPLIT_PROFILE_OF` | ❌ Missing | `UnitParser` does not emit this edge. |
| `HAS_COMPOSITION_RULE` | ❌ Missing | `ArmyListParser` does not emit this edge. |
| `CLARIFIES` → Unit/Spell/Weapon/Terrain | ⚠️ Partial | Coordinator text-match pass only targets rules; schema says FAQ should also clarify Unit, Spell, Weapon, Terrain, MagicItem. |
| `AMENDS` → Unit/MagicItem/Terrain | ⚠️ Partial | Same as above for Errata. |
| `HAS_OPTIONAL_RULE` | ✅ Present | Emitted by `UnitParser` from options/optionalRules fields. |
| `HAS_INTRINSIC_RULE` | ⚠️ Seed only | `rule_parser.py` mentions it but relies on seed; no dynamic extraction from troop type pages. |

---

## 3. 50-Query Coverage Analysis

Each query is rated: ✅ fully answerable, ⚠️ partial (needs text inference),
❌ not answerable with current graph structure.

### Rules & Mechanics Queries (25)

| # | Query | Rating | Required Nodes/Edges |
|---|-------|--------|---------------------|
| 1 | "What does the Fear special rule do?" | ✅ | `:SpecialRule {id: "fear"}` → text |
| 2 | "How does Regeneration interact with Flaming Attacks?" | ✅ | `:SpecialRule` "regeneration" + "flaming-attacks" → `REFERENCES` traversal |
| 3 | "What happens when a unit with Stubborn takes a Break test?" | ✅ | `:SpecialRule {id: "stubborn"}` → text |
| 4 | "Can a unit with Fly charge over enemy units?" | ⚠️ | `:SpecialRule {id: "fly"}` → text (mentions terrain immunity); TERRAIN_INTERACTION seed exists but Terrain nodes missing |
| 5 | "What is the maximum rank bonus for Heavy Infantry?" | ✅ | `:TroopType {id: "heavy-infantry"}` → max_rank_bonus: 2 |
| 6 | "How many models for a rank bonus in Swarms?" | ✅ | `:TroopType {id: "swarms"}` → min_models_for_rank_bonus: null |
| 7 | "What unit strength does Monstrous Cavalry have?" | ✅ | `:TroopType {id: "monstrous-cavalry"}` → unit_strength_per_model: 3 |
| 8 | "How does the Magic phase work?" | ✅ | `:CoreRule {id: "the-magic-phase"}` → text |
| 9 | "What's the difference between Magic Missile and Magical Vortex?" | ⚠️ | Text exists but `spell_type` is null on all spells |
| 10 | "Can you dispel a Remains in Play spell in your own magic phase?" | ✅ | `:CoreRule` → text, via vector search |
| 11 | "What happens when a unit is Disrupted?" | ✅ | `:CoreRule` or `:SpecialRule` → text |
| 12 | "How do Cannon balls bounce?" | ⚠️ | `:Weapon {id: "cannon"}` → text only; bounce field is null |
| 13 | "What's the casting value for Invocation of Nehek?" | ✅ | `:Spell {id: "invocation-of-nehek"}` → casting_value |
| 14 | "What spells are in the Lore of Necromancy?" | ✅ | `:Lore` ← BELONGS_TO_LORE ← `:Spell` |
| 15 | "Does a shield give +1 to armour save?" | ⚠️ | `:Weapon {id: "shield"}` → text only; armour_value is null |
| 16 | "What is the armour value of full plate armour?" | ⚠️ | `:Weapon {id: "full-plate-armour"}` → text only |
| 17 | "How does the Ethereal special rule work?" | ✅ | `:SpecialRule {id: "ethereal"}` → text |
| 18 | "Does Ethereal ignore dangerous terrain?" | ❌ | TERRAIN_INTERACTION seed exists (Ethereal → dangerous-terrain) but `:Terrain` node missing |
| 19 | "Can Scouts deploy in woods?" | ❌ | TERRAIN_INTERACTION seed exists (Scouts → woods) but `:Terrain` node missing |
| 20 | "What are the rules for Open Ground?" | ❌ | No `:Terrain {id: "open-ground"}` node |
| 21 | "What terrain disrupts units?" | ❌ | No `:Terrain` nodes → can't query `disrupts_units = true` |
| 22 | "Is cover granted by woods partial or full?" | ❌ | No `:Terrain {id: "woods"}` → `grants_cover` |
| 23 | "What's the FAQ about rerolls being discarded?" | ✅ | `:FAQ` → text |
| 24 | "What errata changed the Steam Tank rules?" | ✅ | `:Errata` → text + CLARIFIES/AMENDS traversal |
| 25 | "What version is the latest FAQ from?" | ✅ | `:FAQ` → source_version |

### Army Building Queries (25)

| # | Query | Rating | Required Nodes/Edges |
|---|-------|--------|---------------------|
| 26 | "Build me a 2000pt Vampire Counts list" | ✅ | `:Army` + HAS_UNIT ← `:Unit` + HAS_UPGRADE → `:Upgrade` + `:CompositionList`/Slot |
| 27 | "What units are available in the Empire of Man?" | ✅ | `:Army` ← BELONGS_TO ← `:Unit` |
| 28 | "What special rules do Blood Knights have?" | ✅ | `:Unit {id: "blood-knights"}` → HAS_RULE → `:SpecialRule` |
| 29 | "How much do Blood Knights cost per model?" | ✅ | `:Unit {id: "blood-knights"}` → cost_points_per_model |
| 30 | "What's the base size of a Steam Tank?" | ✅ | `:Unit` → base_width_mm, base_depth_mm |
| 31 | "What equipment do Grave Guard come with by default?" | ✅ | `:Unit` → HAS_WEAPON → `:Weapon` |
| 32 | "What upgrades can I give to Skeleton Warriors?" | ✅ | `:Unit` → HAS_UPGRADE → `:Upgrade` |
| 33 | "How much to give shields to 20 Clanrats?" | ✅ | `:Upgrade` "shield" → points_cost × 20 |
| 34 | "Can a Vampire Lord take magic items? How many points?" | ✅ | `:Upgrade {upgrade_type: "magic_item_budget"}` → points_budget |
| 35 | "What magic items can a Tomb King take?" | ✅ | `:Unit` → CAN_TAKE_ITEM (derived) → `:MagicItem` |
| 36 | "Does my Wizard have access to Lore of Necromancy?" | ✅ | `:Unit` → USES_LORE → `:Lore {id: "necromancy"}` |
| 37 | "What mount options does a Chaos Lord have?" | ✅ | `:Unit` → HAS_UPGRADE → `:Upgrade` → UNLOCKS_MOUNT → `:Unit` |
| 38 | "How much does a barded Nightmare cost as a mount?" | ✅ | `:Upgrade {upgrade_type: "mount"}` → points_cost |
| 39 | "What's the profile of a Zombie Dragon?" | ✅ | `:Profile` node via HAS_PROFILE |
| 40 | "Can I take a Battle Standard Bearer?" | ✅ | `:CompositionList` → `:Upgrade {upgrade_type: "command_bsb"}` |
| 41 | "What percentage of my army can be Characters?" | ✅ | `:CompositionSlot {slot_name: "Characters"}` → max_pct |
| 42 | "Which armies can ally with Vampire Counts?" | ✅ | `:Army` → ALLIED_WITH → `:Army` |
| 43 | "Difference between trusted and suspicious allies?" | ⚠️ | Alliance type on edge exists, but rules text for each level is in CoreRule text |
| 44 | "How many points of magic items can my champion take?" | ⚠️ | `command_champion` upgrade exists but budget not profile-scoped in CAN_TAKE_ITEM derivation |
| 45 | "Can a unit standard bearer take a magic standard?" | ⚠️ | `magic_standard_budget` may not be detected when embedded in standard bearer descriptive line |
| 46 | "What Great Weapons does this unit swap to?" | ✅ | `:Upgrade {upgrade_type: "weapon_replace"}` → replaces_weapon_id |
| 47 | "What troops can I bring as Mercenaries?" | ✅ | `:CompositionSlot` → SLOT_ALLOWS → `:Unit` |
| 48 | "What's the split profile for a Demigryph Knight?" | ⚠️ | HAS_PROFILE edges exist for both rider and mount, but SPLIT_PROFILE_OF missing |
| 49 | "What's a Varghulf's WS and attacks?" | ✅ | `:Profile {id: "varghulf#varghulf"}` → WS, A |
| 50 | "Is a named character required to include its unit?" | ⚠️ | `is_named_character: true` exists, but the rule about named character force multipliers is in text |

### Summary

| Rating | Count | Percentage |
|--------|-------|-----------|
| ✅ Fully answerable | 35 | 70% |
| ⚠️ Partial (text only, or missing structured data) | 10 | 20% |
| ❌ Not answerable (missing nodes) | 5 | 10% |

All 5 failures trace to missing `:Terrain` nodes.
All 10 partials trace to:
- Missing weapon/spell structured fields (queries 9, 12, 15, 16)
- Missing `SPLIT_PROFILE_OF` (query 48)
- Missing champion magic item budget scoping (query 44)
- Missing standard bearer magic standard budget detection (query 45)
- Alliance rules text only (query 43)
- Named character rules text only (query 50)
- Terrain interaction without Terrain nodes (query 4)

---

## 4. What IS Working Well

### Data Completeness

| Category | Covered? | Details |
|----------|----------|---------|
| All 19 armies | ✅ | `ArmyParser` extracts name, slug, rules, weapons, lores, magic items |
| All unit pages | ✅ | `UnitParser` extracts cost, category, troop type, base size, unit size, wizard level, AV, profiles |
| All special rules | ✅ | `RuleParser` with `rule_scope` and `army_id` |
| All core rules | ✅ | `CoreRuleParser` with section/section_id, prev/next navigation |
| All troop types | ✅ | `RuleParser` with TROOP_TYPE_SEED enrichment |
| All weapons | ✅ | `WeaponParser` with weapon_class inference |
| All magic items | ✅ | `MagicItemParser` with item_type normalisation, army_id from association |
| All spells | ✅ | `SpellParser` handles both standard (embedded-entry-block) and renegade (richtext) formats |
| All lores | ✅ | `SpellParser` emits Lore + Spell nodes + BELONGS_TO_LORE edges |
| All FAQs | ✅ | `FAQParsers` extracts question, answer, source_version, source_document |
| All errata | ✅ | `ErrataParser` extracts original_text, corrected_text, source |
| All composition lists | ✅ | `ArmyListParser` extracts slot caps, SLOT_ALLOWS, ALLIED_WITH, BSB upgrades |
| Unit upgrades | ✅ | `_options.py` classifies: budgets, wizard levels, command upgrades, mounts, weapon swaps, armour |

### Upgrade Parsing (`_options.py`)

Correctly classifies these upgrade types from rich-text:
- **Budgets:** `magic_item_budget`, `magic_standard_budget`, `vampiric_powers_budget`, `rune_budget`
- **Wizard levels:** "May be a Level 2 Wizard (+35 points)"
- **Command:** `command_champion`, `command_standard`, `command_musician`
- **Mounts:** via `armyListEntry` Contentful links
- **Weapon swaps:** "Replace X with Y (+N pts)" → `weapon_replace` with `replaces_weapon_id`
- **Armour addition:** heavy armour, full plate, barding, shields → `armour_add`
- **Catch-all:** `rule_add` for everything else, promoted to `weapon_add` by two-pass

### Edge Derivation

- **CAN_TAKE_ITEM:** Three idempotent MERGE passes after full graph load:
  1. Characters with `magic_item_budget` / `command_bsb` → common + army-specific items
  2. Units with `magic_standard_budget` → magic_standard items
  3. Units with `vampiric_powers_budget` / `rune_budget` → ability items
- **Two-pass coordinator:** `UNLOCKS_RULE` → `UNLOCKS_WEAPON` / `UNLOCKS_ITEM` based on destination node type; `rule_add` → `weapon_add` for upgrades with weapon/mount edges

### Infrastructure Quality

- **Idempotency:** All writes are MERGE-based. Re-running `make build-graph` produces zero duplicates.
- **Validation:** 10 integrity checks covering node counts, edge drops, orphan
  detection, dangling references, upgrade classifier ratio, profile scope
  resolution, army CAN_TAKE_ITEM coverage, unreachable magic items, FAQ/Errata
  link coverage, intrinsic rule edges. Threshold-based error detection with 5%
  drop limit.
- **Parse-time flattening:** All nested maps flattened to scalars. Loader stays
  simple (`UNWIND + MERGE + SET n += row`) with no transforms.
- **Profiles as nodes:** 945 `:Profile` nodes queryable in Cypher for stat
  comparisons (e.g., `WHERE p.WS >= 5 AND p.A >= 3`).
- **Resumability:** Embedding generation uses `WHERE n.embedding IS NULL`.
- **Neo4j integration:** Containerized with healthcheck, named volumes,
  connection retry with exponential backoff.

### Testing

| Test File | Content | Status |
|-----------|---------|--------|
| `test_parser_flattening.py` | 13 tests on BaseParser helpers + UnitParser flattening | ✅ Passing |
| `test_options_parsing.py` | 30+ tests on `_options.py` classifiers | ✅ Passing |
| `test_classification_pass.py` | 13 tests on two-pass edge relabeling | ✅ Passing |
| `test_embedding_text.py` | 20+ tests on per-label embedding text builders | ✅ Passing |
| `test_chat_stream.py` | 2 tests on Vercel AI SDK streaming protocol | ✅ Passing |
| `test_graph_build.py` | 15 integration tests with testcontainers | ✅ Passing |
| `test_queries.json` | 3 golden evaluation queries | ✅ Defined |
| `test_parsers.py` | Stub | ❌ TODO |
| `test_retriever.py` | Stub | ❌ TODO |
| `test_graph_builder.py` | Stub | ❌ TODO |
| `evaluate.py` | Stub | ❌ TODO |
| `test_pipeline.py` | Stub | ❌ TODO |

---

## 5. Priority Fixes

### Immediate (blocks query answering)

1. **Add `:Terrain` nodes** — Blocks 5 queries and all terrain interaction queries.
   - `NodeType.TERRAIN` in constants
   - `NODE_TYPE_TO_LABEL["terrain"] = "Terrain"`
   - URL pattern `battlefield-terrain/*` in `classify_url()`
   - `TerrainParser` extracting `terrain_class`, `blocks_movement`, `disrupts_units`, etc.
   - Coordinator output to `terrain.json`

2. **Emit `SPLIT_PROFILE_OF` edges** — Distinguishes mount profiles from rider profiles.
   - In `UnitParser`, when a profile name matches a known mount, emit edge from mount profile → rider unit.

### Short-term (improves answer quality)

3. **Fix `magic_standard_budget` on `command_standard` upgrades**
   - After `_STANDARD_RE` match, run `_MAGIC_STANDARD_BUDGET_RE` on the same text.

4. **Profile-scope champion magic item budgets**
   - Set `points_budget` on `command_champion` upgrades when text contains "may take up to N points of magic items."
   - Or add `applies_to_profile` filtering to `_derive_can_take_item()`.

5. **Weapon/spell structured field enrichment**
   - Regex pass over `bodyIndex` / `description` for weapons: `range`, `strength`, `ap`, `armour_value`, `shots`, `template_type`, `bounce`, `special_rules`.
   - Regex pass over spell `description` / `body` for `spell_type`, `duration`, `target`.

### Longer-term (coverage)

6. **Full alliance seed** — Expand from 5 to full allied contingents from each army's composition page.
7. **Full terrain interaction seed** — Complete the mapping from every special rule to terrain effects.
8. **`CLARIFIES`/`AMENDS` extended targets** — Coordinator text-match pass should also link FAQ/Errata to Unit, Spell, Weapon, Terrain, MagicItem nodes.
9. **`HAS_COMPOSITION_RULE` edges** — Link army → army-list CoreRule page.
10. **`HAS_INTRINSIC_RULE` dynamic extraction** — Parse intrinsic rules from troop type pages, not just seed.
