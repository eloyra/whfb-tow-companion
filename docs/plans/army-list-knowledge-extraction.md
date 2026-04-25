# Army-List Game Knowledge Extraction — Plan

*Focused plan for parsing, modeling, and querying the army-list mechanics needed to answer player questions about: unit champions / standard bearers / musicians, Battle Standard Bearer eligibility and cost, mounts, magic items + budgets, magic standards + budgets, mundane equipment, special-rule purchases, and per-character / per-army item access. Companion verification work for the already-implemented Steps A–G (live `make build-graph`, embeddings smoke test, validator comment fix, etc.) is **moved to `docs/plans/graph-and-embeddings-execution.md`** so this plan stays scoped to the new ingest.*

---

## Context — why this plan exists

The user's questions are army-list reasoning questions:

> "Can a Wight King take a magic weapon? How many points?" — needs character → item-budget link AND item-type filter AND faction-item filter.
>
> "Build me a 2000-pt Empire list with a Battle Standard Bearer and two Wizard Lords." — needs army composition slot limits AND BSB-eligibility per character AND wizard-level upgrade options.
>
> "What does a champion / standard bearer / musician cost in a unit of Grave Guard? Can the Seneschal buy magic items?" — needs command-group upgrades with per-unit cost AND profile-scoped item budgets.
>
> "What mounts can a Vampire Count purchase?" — needs mount upgrades with cost, not just a CAN_MOUNT edge.

Right now the graph cannot answer any of these. The parser captures unit pages but discards 90% of the upgrade structure. Three distinct game-knowledge layers are missing:

1. **Per-unit upgrade options** — champion / standard / musician costs, mount costs, item budgets, optional-rule purchases — *all in `unit.fields.options`* but currently flattened into bare `HAS_OPTIONAL_RULE` edges with empty `properties: {}`.
2. **Per-army composition rules** — slot caps (Characters 50% max, Core 25% min, …), 0-1-per-1000 rules, BSB upgrade and cost, allowed allies — *all in army-list `:CoreRule` pages* (`<army>-army-list.html`) but currently captured only as flat prose in `:CoreRule.text`.
3. **Item access modeling** — which character can take which item and from which pool — derivable from existing `:MagicItem` properties (`item_type`, `army_id`) plus the new `:Upgrade` data, but only if the graph supports the join.

The data exists in the source. Nothing new needs to be scraped. This plan describes the parse-time and graph-time work to surface it.

---

## Source-data analysis (read directly during planning)

### 1. Unit upgrade options — `unit.fields.options` (Contentful rich-text)

Inspected raw `__NEXT_DATA__` of vampire-count, vampire-thrall, wight-king, grave-guard, royal-clan-warriors, royal-herald, black-orc-warboss. Consistent grammar:

```
vampire-count.options:
  May take one of the following: [rule:two-hand-weapons-…] (+3 pts) | [rule:great-weapon] (+4) | [rule:lance] (+4)
  May take a [rule:shield] (+2 points)
  May take one of the following: [rule:light-armour] (+3) | [rule:heavy-armour] (+6)
  May be mounted: [armyListEntry:nightmare] (+16) | [armyListEntry:coven-throne] (+210) | …
  Be a Level 1 Wizard (+30 points) | Be a Level 2 Wizard (+60 points)
  Purchase magic items up to a total of 100 points
  Take [rule:vampiric-powers] up to a total of 100 points

grave-guard.options:
  The entire unit may replace [rule:shield] with [rule:great-weapon]s (+1 point per model)
  Any unit may:
    Upgrade one model to a Seneschal (champion) (+6 points per unit)
    Upgrade one model to a standard bearer (+6 points per unit)
    Upgrade one model to a musician (+6 points per unit)
    Purchase a magic standard worth up to 50 points
    A Seneschal may purchase magic items up to a total of 25 points
  0-1 unit per 1,000 points may:
    Have the [rule:drilled] special rule (+2 points per model)
    Have the [rule:implacable-defence] special rule (+1 point per model)

royal-clan-warriors.options (Dwarfen rune-budget terminology):
  …
  Purchase [rule:standard-runes] up to a total of 75 points
  A Royal Clan Veteran may purchase:
    [rule:weapon-runes] up to a total of 25 points
    [rule:talismanic-runes] up to a total of 25 points
```

Patterns to detect:
- Cost: `\(\s*\+(\d+)\s*point[s]?(?:\s+per\s+(model|unit))?\s*\)` → `points_cost`, `cost_unit ∈ {per_model, per_unit, flat}`.
- Budget: `up\s+to\s+a\s+total\s+of\s+(\d+)\s+points` → `points_budget`, `cost_unit = "budget"`.
- Wizard: `Be a Level (\d+) Wizard` → `upgrade_type = "wizard_level"`.
- Champion: `Upgrade one model to (?:a |an )?<name>(?:\s*\(champion\))?` → `command_champion`, `name = <name>`.
- Standard: `Upgrade one model to a standard bearer` → `command_standard`.
- Musician: `Upgrade one model to a musician` → `command_musician`.
- Equipment swap: `replace [rule:X] with [rule:Y]` → `equipment_swap`, store both via `replaces_weapon_id` + `UNLOCKS_WEAPON` edge.
- Mount: parent header is `May be mounted` OR sole hyperlink content-type is `armyListEntry` → `mount`.
- Magic-item-class budget: budget leaf + linked rule slug ∈ {`vampiric-powers`, `weapon-runes`, `armour-runes`, `standard-runes`, `talismanic-runes`} → `vampiric_powers_budget` / `rune_budget`. Plain text contains "magic items" → `magic_item_budget`. Plain text contains "magic standard" → `magic_standard_budget`.
- Constraint headers: `0-1 unit per 1,000 points may:` → set `availability_constraint` for all leaves under that header. `if appropriately mounted` / `Nomadic Waaagh! only` / `if a level 4 wizard` → captured as inline constraint text on the leaf.
- Profile-scoped budgets: header `^A[n]? ([\w \-]+) may` where the captured name slugifies to a sibling profile id (`grave-guard#seneschal`) → set `applies_to_profile`.
- Mutex grouping: every `May take one of the following:` increments a counter → siblings share `mutex_group = "<unit-slug>#mg<n>"`.

### 2. Army-list composition — `<army>-army-list.html` (Contentful rich-text body)

Inspected `empire-of-man-army-list.html`. Body uses `heading-2` ("Grand Army Composition List") and `heading-3` ("Characters", "Core", "Special", "Rare", "Mercenaries", "Allies", "Battle Standard Bearer", and sometimes "Magic Items") sections. Each section's paragraphs hold entry-hyperlinks to specific units/rules with prose constraints.

**BSB extraction example** (heading-3 "Battle Standard Bearer"):

> *"A single [LINK:captain-of-the-empire]Captain of the Empire in your army may be upgraded to be your [LINK:the-battle-standard]Battle Standard Bearer for +25 points. In addition to their usual allowance of points to spend on magic items, a Battle Standard Bearer can purchase a single magic standard with no points limit."*

Extractable: eligible character slug (from entry-hyperlink), cost (regex `\+(\d+) points`), unlimited-magic-standard flag (regex `magic standard with no points limit` / `unlimited magic standard`).

**Slot-cap extraction** (heading-3 "Characters", "Core", etc.): the leading paragraph carries percentage/minimum text — regex `Up to (\d+)%`, `At least (\d+)%`. Sub-list entries name the units allowed in the slot (entry-hyperlinks) plus per-1000-pts constraints (regex `0-(\d+) (?:[\w\- ]+) per (\d[,\d]*) points`).

19 army-list pages exist (`beastmen-brayherds-army-list.html` … `wood-elf-realms.html`). All share this structure (verified for Empire; spot-check during implementation).

### 3. Magic item access — `data/parsed/magic_items.json` already has the data we need

```
698 items total. item_type distribution:
   138 magic_weapon       128 magic_standard      125 ability
    82 enchanted_item      82 arcane_item          67 magic_armour
    63 talisman            13 unique
army_id distribution (top): ravening-hordes 249 | forces-of-fantasy 132 | None 67
                            daemons-of-chaos 39 | grand-cathay 36 | ogre-kingdoms 25 | …
```

`item_type` values map to access rules well-known in WHFB:
- `magic_weapon`, `magic_armour`, `talisman`, `enchanted_item` → any character with a magic-item budget can buy.
- `arcane_item` → wizards only (per `arcane-items.html`: *"Only Wizards can purchase Arcane Items."*).
- `magic_standard` → only the standard bearer of a unit, capped by that unit's `magic_standard_budget`.
- `ability` (e.g. Vampiric Powers, Big Names, Knightly Virtues) → army-specific category, gated by a separate budget upgrade.
- `unique` → one per army.

`army_id`:
- `ravening-hordes` / `forces-of-fantasy` → **common pool**, available to any army.
- `<army-slug>` → **faction pool**, only that army's characters.
- `None` (67 items) → audit; likely common items mis-classified or named-character items. Out of scope to fix in this plan; flag in validator.

Some items embed restrictions in body text (e.g. *"Wood Elf Nobles and Mages only"*) — no structured field captures this. Strategy: keep the existing `:MagicItem.text` (already populated for 698/698) and let the LLM read it for fine-grained restrictions; the graph filters by `item_type` + `army_id` + character flags only.

### 4. Mundane equipment — already covered

`:Weapon` nodes (264) carry mundane gear (hand weapon, shield, light armour, …). Existing `HAS_WEAPON` (1,642 edges) captures standard equipment. Optional weapon purchases are mis-typed as `HAS_OPTIONAL_RULE` because Contentful tags weapons as content-type `rule`. Will be fixed by the two-pass classifier in §Phase 1.

---

## Phase 1 — `:Upgrade` ingest from `unit.fields.options`

### Goal

For every unit page, emit one `:Upgrade` node per leaf option in `options`, preserving cost / cost_unit / mutex_group / applies_to_profile / budget / constraint / order, plus typed `UNLOCKS_*` edges to the linked weapon / item / rule / mount.

### Schema

`:Upgrade` node properties (extends schema doc L511–545):

| Property | Type | Notes |
|---|---|---|
| `id` | str | `<unit-slug>#upgrade-<n>` |
| `url` | str | parent unit url |
| `name` | str | derived label, e.g. "Champion (Seneschal)", "Great weapon", "Nightmare mount" |
| `description` | str | leaf plain text trimmed |
| `upgrade_type` | enum | `command_champion` / `command_standard` / `command_musician` / `command_bsb` / `mount` / `weapon_add` / `weapon_replace` / `armour_add` / `wizard_level` / `magic_item_budget` / `magic_standard_budget` / `vampiric_powers_budget` / `rune_budget` / `rule_add` (catch-all) |
| `points_cost` | int \| null | absolute or per-model/-unit value when present |
| `cost_unit` | enum | `per_model` / `per_unit` / `flat` / `budget` |
| `points_budget` | int \| null | set when `cost_unit == "budget"` |
| `mutex_group` | str \| null | shared id among siblings under "May take one of the following" |
| `applies_to_profile` | str \| null | profile slug (`<unit-slug>#seneschal`) when scoped to a champion |
| `availability_constraint` | str \| null | verbatim "0-1 unit per 1,000 points", "if appropriately mounted", … |
| `replaces_weapon_id` | str \| null | for `weapon_replace`, slug of replaced weapon |
| `order` | int | stable position in source for ORDER BY |
| `source_citation_book`, `source_citation_page` | str / int \| null | inherited from unit |

### New `EdgeType` constants (`pipeline/constants.py`)

`HAS_UPGRADE`, `UNLOCKS_RULE`, `UNLOCKS_WEAPON`, `UNLOCKS_ITEM`, `UNLOCKS_MOUNT`, `REPLACES_WEAPON`. (All already named in `docs/schema/knowledge_graph_schema.md` L606–610; only new in code.)

### New parser module — `pipeline/scraper/parsers/_options.py`

Pure function `parse_options_to_upgrades(unit_slug, options_richtext, profile_slug_set, source_citation) -> (list[upgrade_dict], list[edge_dict])`.

Algorithm:
1. Walk top-level rich-text `content` depth-first; track:
   - `header_stack` (preceding paragraph siblings used as group headers)
   - `mutex_counter` (incremented per "May take one of the following:")
   - `scope_profile` (when a header is `^A[n]? <name> may` and `slugify(name) ∈ profile_slug_set`)
   - `availability_constraint` (set on `0-N unit per …` headers, propagates to all leaves until the next sibling group)
2. Each `list-item` whose paragraph contains either a cost annotation or a budget phrase is a leaf upgrade. Collect:
   - `entry_links: list[(slug, contentType)]` via existing `_richtext_entry_links_typed`
   - `text: str` via `_richtext_to_text`
3. Apply classifier regexes (in priority order: budget → wizard → champion → command → mount → swap → cost → catch-all) to determine `upgrade_type`, `points_cost`, `cost_unit`, `points_budget`, `replaces_weapon_id`, derived `name`.
4. Emit one `:Upgrade` node + `HAS_UPGRADE` edge from unit. For each entry link: emit a provisional edge:
   - `armyListEntry` → `UNLOCKS_MOUNT`
   - `rule` → provisional `UNLOCKS_RULE` (re-typed in coordinator post-pass)

### Two-pass classification (coordinator — `pipeline/scraper/parsers/__init__.py`)

After all parsers finish, before writing files:
- Build slug sets `_weapon_slugs`, `_item_slugs`, `_rule_slugs` from the parsed records.
- For every provisional `UNLOCKS_RULE` edge:
  - dst ∈ `_weapon_slugs` → relabel `UNLOCKS_WEAPON`
  - dst ∈ `_item_slugs` → relabel `UNLOCKS_ITEM`
  - else stays `UNLOCKS_RULE`
- Same lookup decides budget sub-type when ambiguous.

This pass is O(edges), runs before writing `edges.json`. No Neo4j needed.

### Modify `unit_parser.py`

- Compute `profile_slug_set` from `unitProfile` (using existing `_name_to_slug`).
- Call `parse_options_to_upgrades(...)`; merge results into `ParseResult`.
- **Keep** existing `HAS_OPTIONAL_RULE` and `CAN_MOUNT` edges — they're additive context for the RAG layer; removing them is a breaking change.

### DDL (`pipeline/graph/ddl.py`)

- `CREATE CONSTRAINT upgrade_id IF NOT EXISTS FOR (n:Upgrade) REQUIRE n.id IS UNIQUE`
- Btrees: `:Upgrade(applies_to_profile)`, `:Upgrade(upgrade_type)`, `:Upgrade(mutex_group)`

### Loader (`pipeline/graph/builder.py`)

Insert `upgrades.json` in fixed load order between `profiles.json` and `special_rules.json`.

### Embedding text (`pipeline/embeddings/text.py`)

Extend `_build_unit_text` Cypher to fetch upgrades and append a segment:

```
Upgrades — Champion (Seneschal): +6 pts/unit; Standard: +6 pts/unit;
Magic standard up to 50 pts; Drilled: +2 pts/model; …
```

This makes upgrade-driven queries findable via the unit-scoped vector index.

### Tests

- `tests/unit/test_options_parsing.py` — fixtures from vampire-count, grave-guard, royal-clan-warriors, royal-herald `options` payloads. Assert upgrade count, `upgrade_type` distribution, specific costs, mutex_group cardinality, `applies_to_profile == "grave-guard#seneschal"`.
- `tests/unit/test_classification_pass.py` — synthetic coordinator test: provisional `UNLOCKS_RULE` edges to weapon / item / rule slugs are retyped correctly.
- Extend `tests/integration/test_graph_build.py` with a synthetic Upgrade record + assertions.

### Verification

```bash
make parse                        # regenerates data/parsed/, including upgrades.json
python -c "import json; from collections import Counter; \
  ups = json.load(open('data/parsed/upgrades.json')); \
  print(len(ups), Counter(u['upgrade_type'] for u in ups).most_common())"
# Expect ~3000-5000 upgrades, dominated by command_champion/standard/musician,
# mount, magic_item_budget, weapon_add, rule_add.
```

After `make build-graph`:

```cypher
// Vampire Count's full upgrade list
MATCH (u:Unit {id:"vampire-count"})-[:HAS_UPGRADE]->(up:Upgrade)
RETURN up.name, up.upgrade_type, up.points_cost, up.cost_unit, up.points_budget
ORDER BY up.order;
// Expect ~14 rows: 3 weapon options (+3/+4/+4), shield(+2), 2 armour, 4 mount,
// 2 wizard levels, magic_item_budget(100), vampiric_powers_budget(100).

// Grave Guard command group
MATCH (u:Unit {id:"grave-guard"})-[:HAS_UPGRADE]->(up:Upgrade)
WHERE up.upgrade_type STARTS WITH "command_"
RETURN up.name, up.points_cost;
// Expect Seneschal/Standard/Musician each at +6.
```

---

## Phase 2 — Army-list composition extraction from `<army>-army-list.html`

### Goal

Capture the structured composition rules currently buried in `:CoreRule.text` of the 19 army-list pages. Exposes BSB eligibility per army, slot caps (Characters 50% / Core 25% / etc.), allies allowed, and 0-N-per-1000 unit limits.

### New node types

| Node | Description | Why a node, not a property |
|---|---|---|
| `:CompositionList` | One per army-list page. Holds the percentage caps for Characters / Core / Special / Rare / Mercenaries / Allies. | A list is shared by multiple armies via Allied-Contingent rules — keeps eligibility queryable. |
| `:CompositionSlot` | One per (army-list, slot) pair. Holds `slot_name`, `min_pct`, `max_pct`, plus link to the units allowed in that slot. | Lets you query "which Empire units fit the Special slot?" with a single MATCH. |

Edges:
- `HAS_LIST` — `:Army` → `:CompositionList`
- `HAS_SLOT` — `:CompositionList` → `:CompositionSlot`
- `SLOT_ALLOWS` — `:CompositionSlot` → `:Unit` (one per allowed unit)
- `SLOT_HAS_LIMIT` — `:CompositionSlot` → `:CompositionSlotLimit` (carries `unit_id`, `max_count`, `per_points`) for "0-1 X per 1,000 points"-style rules. Modeled as an edge property dict to keep the graph flat — actually, make it an edge property on `SLOT_ALLOWS`: `{max_count: int|null, per_points: int|null}`.

For BSB:
- `:Upgrade` node with `upgrade_type = "command_bsb"`, attached to the eligible character via `HAS_UPGRADE`. Keeps BSB symmetric with the Phase 1 model.
- The army-list parser produces this Upgrade node directly — its `id` is `<character-slug>#upgrade-bsb-<army-slug>` (deterministic, cross-army-safe in case a character is BSB-eligible in multiple lists).

For Allies:
- `ALLIED_WITH` — `:Army` → `:Army` with `alliance_type` enum (`trusted` / `uneasy` / `suspicious`). Already in schema (ADR-0005 §Alliance), seeds file currently has only 5 entries — Phase 2 fills it from the 19 army-list pages, replacing the partial seed.

### New parser — `pipeline/scraper/parsers/army_list_parser.py`

Triggered for `:CoreRule` pages whose slug ends with `-army-list`. Walks the rich-text `body`:

1. Identify each `heading-3` section by its name.
2. For "Characters" / "Core" / "Special" / "Rare" / "Mercenaries":
   - Read the leading paragraph for `Up to (\d+)%` / `At least (\d+)%` → slot caps.
   - For each list-item under the heading: collect entry-hyperlink slugs → `SLOT_ALLOWS` edges. Detect `0-(\d+) … per ([\d,]+) points` patterns on the leaf text → per-edge `{max_count, per_points}` properties.
3. For "Allies":
   - Each entry-hyperlink to another army (or another army-list page) → `ALLIED_WITH` edge with `alliance_type` parsed from inline parenthetical (`Suspicious`, `Trusted`, `Uneasy`) or default `trusted` when absent.
4. For "Battle Standard Bearer":
   - Find entry-hyperlinks of content-type `armyListEntry` (or `rule` resolving to a known unit slug) → eligible character.
   - Regex `\+(\d+) points` → `points_cost`.
   - Regex `magic standard with no points limit|no points limit` → set new property `bsb_unlimited_magic_standard: True` on the Upgrade.
   - Emit a `:Upgrade` node with `upgrade_type = "command_bsb"` + `HAS_UPGRADE` edge from the eligible character.
5. For "Magic Items" (when present): some armies' army-list pages override default item access (e.g. "Wizards may take Arcane Items up to 50 pts in addition to their normal allowance"). Capture as a `:CompositionSlot` row with `slot_name = "magic_item_override"` and a free-form `text` property — the LLM uses this prose; the graph just makes it retrievable from the army.

### Modify coordinator

- Route `:CompositionList` and `:CompositionSlot` records to new files `composition_lists.json` and `composition_slots.json`.
- Extend the BSB upgrade emission to land in the existing `upgrades.json`.

### DDL additions

Constraints + btrees for `:CompositionList`, `:CompositionSlot`. Composition lists are not embeddable (they are pure structure).

### Verification

```cypher
// Empire BSB rule
MATCH (u:Unit {id:"captain-of-the-empire"})-[:HAS_UPGRADE]->(up:Upgrade {upgrade_type:"command_bsb"})
RETURN u.name, up.points_cost, up.bsb_unlimited_magic_standard;
// Expect: Captain of the Empire | 25 | true

// Empire allies
MATCH (a:Army {id:"empire-of-man"})-[r:ALLIED_WITH]->(b:Army)
RETURN b.id, r.alliance_type;
// Expect: dwarfen-mountain-holds, grand-cathay, kingdom-of-bretonnia, wood-elf-realms (suspicious)

// Vampire Counts Special slot
MATCH (a:Army {id:"vampire-counts"})-[:HAS_LIST]->(:CompositionList)
      -[:HAS_SLOT]->(s:CompositionSlot {slot_name:"Special"})-[r:SLOT_ALLOWS]->(u:Unit)
RETURN s.max_pct, u.name, r.max_count, r.per_points
ORDER BY u.name;
```

---

## Phase 3 — Item access modeling (no new ingest, derived edges + helper Cypher)

### Goal

After Phases 1 and 2 land, the graph contains everything to answer item-access queries via Cypher. This phase wires it together with derived edges and a small set of canonical query patterns the RAG retriever will use.

### Derived edges (post-build, in `pipeline/graph/builder.py`)

Run after `loader.load_edges` and before validator:

```cypher
// CAN_TAKE_ITEM — character → magic item
// A character may take an item when:
//   1. They have a magic_item_budget upgrade (or are a BSB), AND
//   2. The item belongs to the common pool OR their army's pool, AND
//   3. The item type is compatible with the character's wizard level / standard-bearer status.
MATCH (u:Unit)-[:HAS_UPGRADE]->(up:Upgrade)
WHERE up.upgrade_type IN ["magic_item_budget","command_bsb"]
MATCH (u)-[:BELONGS_TO]->(a:Army)
MATCH (i:MagicItem)
WHERE (i.army_id IS NULL
       OR i.army_id IN ["ravening-hordes","forces-of-fantasy"]
       OR i.army_id = a.id)
  AND (i.item_type <> "arcane_item" OR u.wizard_level >= 1)
  AND (i.item_type <> "magic_standard")             // standards handled below
  AND (i.item_type <> "ability")                    // abilities handled by separate budget
MERGE (u)-[r:CAN_TAKE_ITEM]->(i)
SET r.budget = up.points_budget,
    r.via_upgrade = up.id;

// Magic standard → only via standard-bearer upgrade with magic_standard_budget
MATCH (u:Unit)-[:HAS_UPGRADE]->(up:Upgrade {upgrade_type:"magic_standard_budget"})
MATCH (u)-[:BELONGS_TO]->(a:Army)
MATCH (i:MagicItem {item_type:"magic_standard"})
WHERE (i.army_id IS NULL
       OR i.army_id IN ["ravening-hordes","forces-of-fantasy"]
       OR i.army_id = a.id)
MERGE (u)-[r:CAN_TAKE_ITEM]->(i)
SET r.budget = up.points_budget,
    r.via_upgrade = up.id;

// Ability-class items (Vampiric Powers, Big Names, Knightly Virtues, Runes)
// gated by their dedicated budget upgrade
MATCH (u:Unit)-[:HAS_UPGRADE]->(up:Upgrade)
WHERE up.upgrade_type IN ["vampiric_powers_budget","rune_budget"]
MATCH (u)-[:BELONGS_TO]->(a:Army)
MATCH (i:MagicItem {item_type:"ability"})
WHERE i.army_id = a.id
MERGE (u)-[r:CAN_TAKE_ITEM]->(i)
SET r.budget = up.points_budget,
    r.via_upgrade = up.id;
```

This produces O(characters × eligible_items) edges. Estimated ~30,000-50,000 `CAN_TAKE_ITEM` edges (much heavier than the current 10), but well within Neo4j's range. The validator counts and reports.

The text-restriction nuance ("Wood Elf Nobles only") is **not** filtered by this derivation — it remains in `:MagicItem.text`. The RAG layer reads the text when surfacing the recommendation; the graph gates only the structural rules. This is intentional: the graph doesn't model every prose-level restriction.

### Validator additions

- Count `CAN_TAKE_ITEM` edges per army; flag armies with zero (data anomaly).
- Count items with `army_id IS NULL` reaching no characters (data anomaly).
- Count Upgrades with unrecognised `upgrade_type` ("rule_add" exceeding 30% of total → likely missed pattern).

### Verification

```cypher
// What magic items can a Wight King take?
MATCH (u:Unit {id:"wight-king"})-[r:CAN_TAKE_ITEM]->(i:MagicItem)
RETURN i.name, i.item_type, i.points_cost, r.budget
ORDER BY i.item_type, i.name;

// How much can a Vampire Lord spend on magic items?
MATCH (u:Unit {id:"vampire-lord"})-[:HAS_UPGRADE]->(up:Upgrade {upgrade_type:"magic_item_budget"})
RETURN up.points_budget;

// Which Empire characters can be a BSB?
MATCH (a:Army {id:"empire-of-man"})<-[:BELONGS_TO]-(u:Unit)
      -[:HAS_UPGRADE]->(up:Upgrade {upgrade_type:"command_bsb"})
RETURN u.name, up.points_cost;
```

---

## Execution order

1. Phase 1 (unit options → `:Upgrade`) — most plumbing; landing this alone already fixes 80% of the user's stated gap.
2. `make parse` → `make build-graph` → spot-check Phase 1 Cypher.
3. Phase 2 (army-list parser) — adds BSB + slot caps + allies; uses the same `:Upgrade` model so embedding/retrieval is uniform.
4. Phase 3 (derived `CAN_TAKE_ITEM` edges) — runs as a post-load step inside `GraphBuilder.build()`.
5. Final verification battery (this plan's §Verification per phase + the audit-residual items moved to `docs/plans/graph-and-embeddings-execution.md`).

---

## Critical files (modify / create)

**Create**
- `pipeline/scraper/parsers/_options.py` — rich-text walker producing :Upgrade records
- `pipeline/scraper/parsers/army_list_parser.py` — composition / BSB / allies extractor
- `tests/unit/test_options_parsing.py`
- `tests/unit/test_classification_pass.py`
- `tests/unit/test_army_list_parser.py`

**Modify**
- `pipeline/constants.py` — `NodeType.UPGRADE` / `COMPOSITION_LIST` / `COMPOSITION_SLOT`; `EdgeType.{HAS_UPGRADE, UNLOCKS_*, REPLACES_WEAPON, HAS_LIST, HAS_SLOT, SLOT_ALLOWS, CAN_TAKE_ITEM}` (CAN_TAKE_ITEM already exists; rest new)
- `pipeline/scraper/parsers/unit_parser.py` — call `_options`, preserve existing edges
- `pipeline/scraper/parsers/__init__.py` — route new files, run two-pass classifier
- `pipeline/scraper/parsers/core_rule_parser.py` (or coordinator) — dispatch `-army-list` slugs to `ArmyListParser`
- `pipeline/graph/ddl.py` — new constraints + btrees
- `pipeline/graph/builder.py` — load order; post-load derived-edge step
- `pipeline/graph/validator.py` — new threshold checks
- `pipeline/embeddings/text.py` — extend unit text builder with Upgrades segment
- `tests/unit/test_embedding_text.py` — assert upgrade segment
- `tests/integration/test_graph_build.py` — synthetic upgrade + BSB + CAN_TAKE_ITEM assertions

**Schema document touch-ups (clarification only — no new shapes)**
- `docs/decisions/ADR-0005-graph-storage-conventions.md` — short addendum noting `:Upgrade`, `:CompositionList`, `:CompositionSlot`, derived `CAN_TAKE_ITEM` edges and the "graph doesn't model prose restrictions" boundary.

---

## Out of scope (explicitly deferred)

- Prose-level item restriction parsing ("Wood Elf Nobles and Mages only"). Stays in `:MagicItem.text` for LLM consumption.
- Mercenaries cross-army contingent rules beyond the Allies edge; mercenary-specific unit upgrades (handled via the unit's own Phase-1 upgrades).
- Modeling Army-of-Infamy variant lists (sub-lists like "Empire of Sigmar's Sons of Empire" inside the Empire of Man page). Treat them as additional `:CompositionList` records hanging off the same army when found.
- Per-rulebook-version diffing of upgrades (FAQ/errata may shift costs). FAQs/Errata are already :FAQ / :Errata nodes; cross-linking to upgrades is a follow-up.
- Live `make build-graph` / `make embed` smoke run — moved to `docs/plans/graph-and-embeddings-execution.md` as the Steps A–G verification residue.
- Validator stale "1,514 PART_OF_SECTION drops" comment fix — same place; it's an existing-code touch-up, not new modeling.

---

## Risks / mitigations

| Risk | Mitigation |
|---|---|
| Heading-3 names vary across army-list pages (e.g. "Lord", "Hero" sometimes used instead of "Characters") | Keep a header-name → slot-name map; spot-check all 19 pages during impl; fallback to fuzzy match. |
| BSB section absent or worded differently in some armies (e.g. Daemons, Tomb Kings) | Parser logs `BSB_SECTION_NOT_FOUND` per army; validator reports armies with no BSB upgrade. Acceptable — some armies genuinely lack a BSB. |
| Unit-options classifier misses a pattern → leaks as `rule_add` catch-all | Validator: `rule_add` ratio > 30% raises. During impl, manually inspect 10 random `rule_add` upgrades to confirm they're true catch-alls. |
| `applies_to_profile` references a profile slug that doesn't match any `:Profile.id` | Validator MATCH-NOT-EXISTS check; logs count, doesn't block. |
| Derived `CAN_TAKE_ITEM` edges explode (50k+) | Acceptable on Neo4j 5.x community with named volumes. If pathological, gate by adding a `LIMIT` per character or move derivation into the retriever (computed at query time). |
| Magic items with `army_id IS NULL` (67 records) get no `CAN_TAKE_ITEM` edges | Validator flags these; manual fix (assign correct army_id at parse time) is a follow-up data-quality pass. |
| Two-pass classifier mis-routes a budget category whose slug isn't in the canonical list | Keep an explicit `_BUDGET_CATEGORY_SLUGS` set in `_options.py`; surfaces unknown slugs as `rule_add` for inspection. |
