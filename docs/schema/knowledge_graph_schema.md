# Knowledge Graph Schema
## Conversational Assistance System — Warhammer: The Old World
**Version:** 3.1
**Graph database:** Neo4j
**Data source:** tow.whfb.app
**Last revised:** 2026-07-03
**Supersedes:** Version 3.0 (2026-02-20)

> **ADR precedence.** This schema is authoritative for node/edge vocabulary, but storage
> shapes (scalar flattening, `:Profile` first-class nodes, i18n column convention) are
> governed by the binding amendments to **ADR-0004** (2026-04-24) and **ADR-0005**
> (2026-04-24, amended 2026-04-26). Where this document and those ADRs disagree, the ADRs
> win. v3.1 re-aligns this document with those amendments and with the actual output of
> `pipeline/scraper/parsers/` as committed.

---

## Changelog — v3.0 → v3.1

v3.0 described several properties as native Neo4j maps (`i18n`, `source_citation`,
`base_size_mm`, `unit_size`, `composition_percentages`) and embedded unit stat profiles as
a `profiles: List<Map>` on the `:Unit` node. ADR-0004 (2026-04-24 amendment) and ADR-0005
flatten all of these to scalar columns / first-class nodes so the graph loader stays a pure
`MERGE`. v3.1 brings the schema document in line with that decision and with the parsed
data actually written to `data/parsed/`.

| # | Change | Driver |
|---|--------|--------|
| 1 | `source_citation` Map → `source_citation_book` + `source_citation_page` scalars | ADR-0004 §amendment |
| 2 | `base_size_mm` Map → `base_width_mm` + `base_depth_mm` scalars | ADR-0004 §amendment |
| 3 | `unit_size` Map → `unit_size_min` + `unit_size_max` scalars | ADR-0004 §amendment |
| 4 | `i18n` Map removed; translations stored as `{field}_{lang}` columns (`name_es`, `text_es`) with English canonical top-level | ADR-0005 §4 |
| 5 | `profiles: List<Map>` removed from `:Unit`; stat sub-profiles are now `:Profile` nodes via `HAS_PROFILE` | ADR-0004 §amendment, ADR-0005 §3 |
| 6 | `composition_percentages` Map removed from `:Army`; modelled as `:CompositionList` + `:CompositionSlot` nodes | ADR-0005 §amendment (2026-04-26) |
| 7 | New labels documented: `:Profile`, `:CompositionList`, `:CompositionSlot` | ADR-0004/0005 |
| 8 | `:Upgrade` property set updated to the ADR-0005 amendment set (matches `data/parsed/upgrades.json`) | ADR-0005 §amendment |
| 9 | Edge table extended: `HAS_PROFILE`, `UNLOCKS_MOUNT`, `HAS_LIST`, `HAS_SLOT`, `SLOT_ALLOWS`; `CAN_TAKE_ITEM` marked derived; `UNLOCKS_WEAPON`/`UNLOCKS_ITEM` marked coordinator-relabelled | ADR-0005 §amendment |
| 10 | Constraints/indexes table re-aligned with `pipeline/graph/ddl.py` | code |
| 11 | Design-principle "Neo4j native map types" removed | ADR-0004 §amendment |

---

## Index
1. [Design principles](#design-principles)
2. [System constants](#system-constants)
3. [Node types](#node-types)
4. [Relationship types](#relationship-types)
5. [Relationship diagram](#relationship-diagram)
6. [Neo4j implementation notes](#neo4j-implementation-notes)

---

## Design principles

- **English as canonical language.** All structural fields and source texts are stored in
  English. Non-English translations are stored as sibling scalar columns (`name_es`,
  `text_es`, …) populated by the translate stage; they are absent (null) until that stage
  runs. Frontends read `coalesce(n.name_es, n.name)`.
- **Scalar-only node properties.** Neo4j node properties are scalars or homogeneous lists
  of scalars. Nested maps are flattened to scalar columns at parse time (ADR-0004). The
  loader is a pure `MERGE` (`SET n += row`) with no transformation.
- **Multilingual embeddings.** A single English 768-d vector per node
  (`n.embedding`) from `paraphrase-multilingual-mpnet-base-v2`; the model maps Spanish
  queries to English nodes without per-language vectors (ADR-0005 §5).
- **Characteristics as constants.** The mapping from profile abbreviations (`WS`, `BS`, …)
  to their `CoreRule` nodes is resolved via a `CHARACTERISTIC_MAP` constant in code, not as
  graph edges, to avoid structural noise.
- **Controlled redundancy.** `troop_type_id` and `unit_category` are stored both as `Unit`
  node properties *and* as `HAS_TYPE` edges, to enable vector-store serialisation without
  graph traversal.
- **Uniqueness constraints on `id`.** Every node label has a uniqueness constraint on `id`.
  B-tree indexes are created only on properties with non-trivial filter/sort load (see
  implementation notes).
- **Terrain as first-class entities.** The terrain categories plus special features are
  modelled as `:Terrain` nodes to enable direct graph traversal for unit-terrain
  interaction queries.
- **Alliance data as edges.** Army-to-army alliance relationships are directed
  `ALLIED_WITH` edges.
- **Node labels follow PascalCase; relationship types follow SCREAMING_SNAKE_CASE.**

---

## System constants

These live in `pipeline/constants.py` (the code is the source of truth; reproduced here for
reference).

```python
# Maps profile abbreviation -> CoreRule node
CHARACTERISTIC_MAP = {
    "M":  {"id": "movement",         "url": "https://tow.whfb.app/model-profiles/movement"},
    "WS": {"id": "weapon-skill",     "url": "https://tow.whfb.app/model-profiles/weapon-skill"},
    "BS": {"id": "ballistic-skill",  "url": "https://tow.whfb.app/model-profiles/ballistic-skill"},
    "S":  {"id": "strength",         "url": "https://tow.whfb.app/model-profiles/strength"},
    "T":  {"id": "toughness",        "url": "https://tow.whfb.app/model-profiles/toughness"},
    "W":  {"id": "wounds",           "url": "https://tow.whfb.app/model-profiles/wounds"},
    "I":  {"id": "initiative",       "url": "https://tow.whfb.app/model-profiles/initiative"},
    "A":  {"id": "attacks",          "url": "https://tow.whfb.app/model-profiles/attacks"},
    "Ld": {"id": "leadership",       "url": "https://tow.whfb.app/model-profiles/leadership"},
}

TERRAIN_CATEGORIES = [
    "open-ground", "difficult-terrain", "dangerous-terrain", "impassable-terrain",
    "low-linear-obstacle", "high-linear-obstacle", "woods", "hills",
    "special-feature", "building", "linear-terrain-feature",
]

SUPPORTED_LANGUAGES = ["en", "es"]
DEFAULT_LANGUAGE    = "en"
```

`NodeType` and `EdgeType` enums in `pipeline/constants.py` are the authoritative label and
relationship vocabulary (reproduced in the node/edge tables below). `EMBEDDABLE_LABELS`
lists the 12 labels that receive an `embedding` property; `:Profile`,
`:CompositionList`, and `:CompositionSlot` are not embedded independently.

---

## Node types

Each node type corresponds to a **Neo4j label**. Properties are scalars or lists of
scalars (ADR-0004). The field sets below match the actual output of
`pipeline/scraper/parsers/` in `data/parsed/`. `_{lang}` translation columns are omitted
from the tables for brevity; they follow the pattern `name_es`, `text_es`, etc., and are
absent (null) until `make translate` runs.

---

### `:Army`
Represents a playable faction. Root node from which all units hang.

```
Properties (data/parsed/armies.json — 19 records)
------------------------------------------------
id                   : String   -- unique slug. e.g. "vampire-counts"
url                  : String   -- "https://tow.whfb.app/army/vampire-counts"
source_citation_book : String
source_citation_page : Integer|null
last_updated         : String   -- ISO 8601
name                 : String   -- "Vampire Counts"  (+ name_es when translated)
```

> **Composition rules.** Army composition percentages (characters/core/special/rare/ally
> caps) are NOT a property of `:Army`. They are modelled as `:CompositionList` +
> `:CompositionSlot` nodes (see ADR-0005 §amendment). Conditional composition text
> ("0-1 Blood Knights per 1,000 pts", Army of Infamy lists) is captured as `CoreRule`
> nodes linked via `HAS_COMPOSITION_RULE`.
>
> **Ally relationships.** `(:Army)-[:ALLIED_WITH {alliance_type}]->(:Army)`.

---

### `:Unit`
Represents units, characters, and mounts. Stat sub-profiles live on separate `:Profile`
nodes (ADR-0005 §3).

```
Properties (data/parsed/units.json — 574 records)
------------------------------------------------
id                        : String       -- unique slug. e.g. "blood-knights"
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
last_updated              : String

cost_points_per_model     : Integer      -- 39
unit_category             : String       -- broad category. e.g. "Cavalry" (also a HAS_TYPE edge)
troop_type_id             : String       -- slug of the :TroopType node (also a HAS_TYPE edge)
army_category             : String|List<String>  -- "Characters" | "Core" | "Special" | "Rare" |
                                                    "Mounts" | "Named Characters"; List when multi-slot
base_width_mm             : Integer      -- 30
base_depth_mm             : Integer      -- 60
unit_size_min             : Integer|null -- 5; null = no explicit lower limit
unit_size_max             : Integer|null -- null = no explicit upper limit; 1 for single models
is_named_character        : Boolean
av_intrinsic              : String|null  -- "5+" | "4+" | null (AV from nature, not equipment)
wizard_level              : Integer|null -- 1 | 2 | 3 | 4 | null
name                      : String       -- (+ name_es when translated)
```

> **Notes:**
> - Stat profiles (M/WS/.../Ld) are NOT on the `:Unit` node. They are `:Profile` nodes
>   connected via `HAS_PROFILE`. Split profiles (rider + mount, chariot + crew) are
>   separate `:Profile` nodes connected to the same `:Unit`; mount↔rider pairing uses
>   `SPLIT_PROFILE_OF`.
> - AV (Armour Value) is NOT a stat. It is derived from equipment + `av_intrinsic`. See
>   the AV calculation recipe under `:Weapon`.
> - Wizard upgrade options ("Be a Level 1 Wizard +30 pts") are `:Upgrade` nodes with
>   `upgrade_type: "wizard_level"`.

---

### `:Profile`  *(added v3.1; ADR-0004 amendment / ADR-0005 §3)*
A stat sub-profile belonging to a `:Unit` (rider, mount, champion, …). First-class node so
Cypher can filter by stat values directly.

```
Properties (data/parsed/profiles.json — 945 records)
---------------------------------------------------
id                        : String       -- "{unit-slug}#{profile-name-slug}", e.g. "blood-knights#kastellan"
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
name                      : String       -- "Kastelan", "Nightmare", ...
order                     : Integer      -- position in the original unitProfile array
M, WS, BS, S, T, W, I, A, Ld : Integer|null  -- null represents "-" (not applicable)
```

> `HAS_PROFILE` carries `order` as an edge property for `ORDER BY` without re-fetching the
> node. `:Profile` is **not embedded** independently; the parent `:Unit` embedding text
> includes the full stat block.

---

### `:TroopType`
Represents the troop types defined in `/troop-types-in-detail/`.

```
Properties (data/parsed/troop_types.json — 40 records)
-----------------------------------------------------
id                        : String       -- slug. e.g. "heavy-cavalry"
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
last_updated              : String
category                  : String       -- "Infantry" | "Cavalry" | "War Beasts" | "Chariots" |
                                           "Monsters" | "War Machines" | "Swarms"
min_models_for_rank_bonus : Integer|null -- null for types with no Rank Bonus
max_rank_bonus            : Integer|null
unit_strength_per_model   : String       -- "1" | "2" | "3" | "5" | "As Starting Wounds"
name                      : String
text                      : String
```

> Intrinsic rules (e.g. Heavy Infantry → "Steady in the Ranks") are `HAS_INTRINSIC_RULE`
> edges to `:SpecialRule`. Rank Bonus eligibility and Unit Strength are computed in
> application code from the stored thresholds/multipliers.

---

### `:SpecialRule`
Universal, army-specific, or unit-unique special rules.

```
Properties (data/parsed/special_rules.json — 643 records)
--------------------------------------------------------
id                        : String       -- slug. e.g. "fear", "necromantic-undead"
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
last_updated              : String
rule_scope                : String       -- "universal" | "army" | "unique"
army_id                   : String|null  -- army slug if rule_scope = "army" or "unique"
name                      : String
text                      : String
```

---

### `:CoreRule`
Core game mechanics (phases, movement, shooting, magic, army composition, …). Distinct
from `:SpecialRule`: a `CoreRule` is a system mechanic, not a rule a unit possesses.

```
Properties (data/parsed/core_rules.json — 1,377 records)
--------------------------------------------------------
id                        : String       -- slug. e.g. "the-charge-move"
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
last_updated              : String
section                   : String       -- parent section name. e.g. "Movement in Detail"
section_id                : String       -- parent section slug
prev_page_url             : String|null
next_page_url             : String|null
name                      : String
text                      : String
```

---

### `:Document`
Wiki pages that are orientation, etiquette, or convention text without meaningful
cross-references. Stored for vector retrieval only; effectively graph-isolated. Which pages
become `:Document` vs `:CoreRule` is controlled by `DOCUMENT_SECTIONS` / `DOCUMENT_PAGES`
constants in `pipeline/constants.py`.

```
Properties (data/parsed/documents.json — 37 records)
----------------------------------------------------
id                        : String
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
last_updated              : String
section                   : String
section_id                : String
prev_page_url             : String|null
next_page_url             : String|null
name                      : String
text                      : String
```

---

### `:Terrain`
A terrain category or specific terrain feature. First-class entity for unit-terrain
interaction queries.

```
Properties (data/parsed/terrains.json — 37 records)
--------------------------------------------------
id                        : String   -- slug. e.g. "difficult-terrain", "woods", "tower"
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
last_updated              : String
terrain_class             : String   -- "open" | "difficult" | "dangerous" | "impassable" |
                                        "low_linear_obstacle" | "high_linear_obstacle" | "woods" |
                                        "hills" | "special_feature" | "building" | "linear_terrain_feature"
movement_penalty          : String|null
blocks_movement           : Boolean
disrupts_units            : Boolean
requires_dangerous_test   : Boolean
grants_cover              : String|null  -- "partial" | "full" | null
special_feature_benefit   : String|null  -- only when terrain_class = "special_feature"
name                      : String
text                      : String
```

**Terrain node catalogue** (canonical categories; the parser also emits specific features
beyond this list):

| id | terrain_class | blocks_movement | disrupts_units | requires_dangerous_test | grants_cover |
|---|---|---|---|---|---|
| open-ground | open | false | false | false | null |
| difficult-terrain | difficult | false | true | false | null |
| dangerous-terrain | dangerous | false | true | true | null |
| impassable-terrain | impassable | true | false | false | null |
| low-linear-obstacle | low_linear_obstacle | false | false | false | "partial" |
| high-linear-obstacle | high_linear_obstacle | true | false | false | "full" |
| woods | woods | false | true | false | "partial" |
| hills | hills | false | false | false | null |
| arcane-monolith | special_feature | true | false | false | null |
| monument-of-glory | special_feature | true | false | false | null |
| dark-ruins | special_feature | true | false | false | null |
| tower | building | true | false | false | "full" |
| building | building | true | false | false | "full" |
| linear-terrain-feature | linear_terrain_feature | false | false | true | null |

---

### `:Lore`
A Lore of Magic.

```
Properties (data/parsed/lores.json — 38 records)
-----------------------------------------------
id                        : String
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
last_updated              : String
name                      : String
text                      : String
```

---

### `:Spell`
Individual spells within a Lore.

```
Properties (data/parsed/spells.json — 139 records)
-------------------------------------------------
id                        : String
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
last_updated              : String
lore_id                   : String       -- slug of the parent :Lore
lore_number               : Integer|null -- 0 = signature; 1-6 = numbered; null if N/A
casting_value             : Integer      -- base casting value
casting_value_boosted     : Integer|null -- enhanced CV (null if N/A)
casting_value_override    : Integer|null -- explicit override when the boosted row is ambiguous
spell_type                : String       -- "Hex" | "Magic Missile" | "Conveyance" | "Enchantment" |
                                           "Assailant" | "Magical Vortex" | "Bound Spell"
range                     : String       -- "Self" | "Combat" | "24" | ...
duration                  : String       -- "Instant" | "Until end of turn" | "Remains in Play" | ...
target                    : String       -- e.g. "enemy unit", "friendly unit", "self"
name                      : String
text                      : String
```

> Spell source-of-truth is the dedicated `/spell/{slug}` page handled by `SpellParser`;
> `LoreParser` emits only `:Lore` + `BELONGS_TO_LORE` edges (ADR-0006).

---

### `:Weapon`
Weapons, armour, and additional equipment.

```
Properties (data/parsed/weapons.json — 264 records)
--------------------------------------------------
id                        : String       -- slug. e.g. "lance", "heavy-armour", "cannon"
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
last_updated              : String
weapon_class              : String       -- "melee" | "missile" | "armour" | "equipment" | "war_machine"
range                     : String|null  -- "Combat" for melee; "24" for missile
strength                  : String|null  -- "S" | "S+2" | "4"
ap                        : String|null  -- "-1", "-2"; null if no AP modifier
special_rules             : List<String> -- rule slugs conferred by this weapon
armour_value              : String|null  -- "5+" | "4+" absolute; "+1" relative; null for non-armour
shots                     : String|null  -- "1" | "D3" | "3D6" (war_machine only)
template_type             : String|null  -- "blast" | "large_blast" | "flame_template" (war_machine only)
is_indirect               : Boolean      -- true for stone throwers (war_machine only)
bounce                    : Boolean      -- true for cannon balls (war_machine only)
name                      : String
text                      : String
```

> **AV calculation recipe:**
> 1. Start from `unit.av_intrinsic` (if not null).
> 2. Override with the highest-tier armour item's absolute `armour_value`
>    (Full Plate Armour "3+" beats Heavy Armour "4+").
> 3. Apply all "+1" modifiers from shields, barding, etc.
> 4. Cap by troop type: infantry/cavalry max 2+; chariots/monsters/war machines max 3+.

---

### `:MagicItem`
Universal magic items and army-specific powers.

```
Properties (data/parsed/magic_items.json — 698 records)
------------------------------------------------------
id                        : String       -- slug. e.g. "sword-of-battle", "dark-acolyte"
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
last_updated              : String
item_type                 : String       -- "magic_weapon" | "magic_armour" | "talisman" |
                                           "magic_standard" | "enchanted_item" | "arcane_item" |
                                           "vampiric_power" | (other army-specific categories)
points_cost               : Integer|null -- null if variable or free
army_id                   : String|null  -- null for universal items
is_single_use             : Boolean
name                      : String
text                      : String
```

> `army_id` is normalised to a real `:Army.id` where the source book maps 1:1 onto a
> single army (`ARCANE_JOURNAL_ASSOCIATION_ARMY_MAP` / `ARCANE_JOURNAL_PAGE_ARMY_OVERRIDES`
> in `pipeline/constants.py`) — raw Contentful association slugs for Arcane Journal
> supplements (e.g. `"arcane-journal-dwarfen-mountain-holds"`) otherwise never match any
> `:Army.id`, silently breaking `CAN_TAKE_ITEM` derivation (`GraphBuilder._derive_can_take_item`
> requires `i.army_id = a.id`). `"ravening-hordes"` and `"forces-of-fantasy"` are intentionally
> left as-is — they are universal books, allow-listed directly in the derivation Cypher. A
> handful of items on niche Army-of-Infamy muster-list pages (no corresponding `:Army` node)
> are intentionally left unmapped.

---

### `:Upgrade`  *(property set updated v3.1; ADR-0005 amendment)*
A purchasable upgrade option for a unit. Emitted from the unit options rich-text by
`_options.py`.

```
Properties (data/parsed/upgrades.json — 2,424 records)
-----------------------------------------------------
id                        : String       -- slug. e.g. "blood-knights-champion"
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
name                      : String
description               : String       -- short label. e.g. "Upgrade one model to a Kastelan"
upgrade_type              : String       -- "command_champion" | "command_standard" | "command_musician" |
                                           "command_bsb" | "weapon_replace" | "weapon_add" | "rule_add" |
                                           "mount" | "wizard_level"
points_cost               : Integer      -- absolute cost
cost_unit                 : String       -- "per_model" | "per_unit" | "fixed"
points_budget             : Integer|null -- magic-item / power budget granted by this upgrade
mutex_group               : String|null  -- mutually-exclusive upgrade group id
applies_to_profile        : String|null  -- :Profile id this upgrade is scoped to (null = whole unit)
availability_constraint   : String|null  -- text of any precondition
replaces_weapon_id        : String|null  -- slug of the weapon being replaced (weapon_replace)
bsb_unlimited_magic_standard : Boolean   -- true for Battle Standard Bearer upgrades
order                     : Integer      -- ordering hint
```

> v3.0 listed `champion_magic_allowance`, `champion_power_allowance`, and
> `magic_standard_budget` on `:Upgrade`. These were **superseded** by the ADR-0005
> amendment set above (`points_budget`, `mutex_group`, `applies_to_profile`,
> `availability_constraint`, `bsb_unlimited_magic_standard`, `order`) and do not appear in
> `data/parsed/upgrades.json`. `:Upgrade` is **not embedded** independently; its names and
> costs are included in the parent `:Unit` embedding text.

---

### `:CompositionList`  *(new v3.1; ADR-0005 amendment)*
One per army Grand Army list. Container for `:CompositionSlot` nodes.

```
Properties (data/parsed/composition_lists.json — 17 records)
-----------------------------------------------------------
id                        : String
url                       : String
army_id                   : String       -- slug of the owning :Army
```

---

### `:CompositionSlot`  *(new v3.1; ADR-0005 amendment)*
A single slot/category within a `:CompositionList` (e.g. "Core", "Special", "Rare").

```
Properties (data/parsed/composition_slots.json — 83 records)
------------------------------------------------------------
id                        : String
army_id                   : String
composition_list_id       : String       -- parent :CompositionList
slot_name                 : String       -- canonical slot name (e.g. "Core", "Special")
min_pct                   : Integer|null
max_pct                   : Integer|null
```

> `SLOT_ALLOWS` edges from `:CompositionSlot` to `:Unit` carry `max_count` and
> `per_points` edge properties.

---

### `:FAQ`
Official FAQ entries.

```
Properties (data/parsed/faqs.json — 244 records)
-----------------------------------------------
id                        : String       -- generated slug
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
last_updated              : String
topic                     : String       -- wiki topic slug. e.g. "movement", "shooting"
source_version            : String       -- e.g. "1.5.2"
source_document           : String       -- "Official Warhammer: The Old World FAQ & Errata" |
                                           "Official Forces of Fantasy FAQ & Errata" |
                                           "Official Ravening Hordes FAQ & Errata"
name                      : String
question                  : String
answer                    : String
```

---

### `:Errata`
Corrections and amendments.

```
Properties (data/parsed/errata.json — 210 records)
-------------------------------------------------
id                        : String
url                       : String
source_citation_book      : String
source_citation_page      : Integer|null
last_updated              : String
source_version            : String
source_document           : String       -- same vocabulary as :FAQ
name                      : String
original_text             : String       -- text before amendment (null if additive)
corrected_text            : String
```

---

## Relationship types

Source of truth: `EdgeType` in `pipeline/constants.py`. Edges are written to
`data/parsed/edges.json` unless noted otherwise.

### Structural relationships

| Relationship | From -> To | Description |
|---|---|---|
| `BELONGS_TO` | `:Unit` -> `:Army` | Unit belongs to a faction |
| `HAS_TYPE` | `:Unit` -> `:TroopType` | Troop type of the unit |
| `HAS_PROFILE` | `:Unit` -> `:Profile` | Stat sub-profile of the unit; edge carries `order` (ADR-0005 §3) |
| `SPLIT_PROFILE_OF` | `:Unit` -> `:Unit` | Sub-unit belongs to parent (mount -> rider) |
| `HAS_RULE` | `:Unit` -> `:SpecialRule` | Always-active special rule |
| `HAS_OPTIONAL_RULE` | `:Unit` -> `:SpecialRule` | Rule granted by an upgrade (optional) |
| `HAS_WEAPON` | `:Unit` -> `:Weapon` | Standard equipment in base cost |
| `HAS_OPTIONAL_WEAPON` | `:Unit` -> `:Weapon` | Weapon available via upgrade (optional) |
| `CAN_MOUNT` | `:Unit` -> `:Unit` | Character can take this mount |
| `CAN_TAKE_ITEM` | `:Unit` -> `:MagicItem` | **Derived post-load** by `GraphBuilder._derive_can_take_item()` (not in `edges.json`); edge carries `budget` and `via_upgrade` (ADR-0005 §amendment) |
| `USES_LORE` | `:Unit` -> `:Lore` | Wizard can generate spells from this lore |
| `BELONGS_TO_LORE` | `:Spell` -> `:Lore` | Spell is part of this lore |
| `PART_OF_SECTION` | `:CoreRule` -> `:CoreRule` | Child rule belongs to parent section |
| `HAS_COMPOSITION_RULE` | `:Army` -> `:CoreRule` | Army-specific composition page text |

### Upgrade relationships

| Relationship | From -> To | Notes |
|---|---|---|
| `HAS_UPGRADE` | `:Unit` -> `:Upgrade` | Purchasable upgrade option |
| `UNLOCKS_RULE` | `:Upgrade` -> `:SpecialRule` | Rule added by upgrade |
| `UNLOCKS_WEAPON` | `:Upgrade` -> `:Weapon` | Weapon added by upgrade — **coordinator-relabelled** from `UNLOCKS_RULE` when `dst` is a weapon slug (ADR-0005 §amendment) |
| `UNLOCKS_ITEM` | `:Upgrade` -> `:MagicItem` | Item category unlocked — **coordinator-relabelled** from `UNLOCKS_RULE` when `dst` is a magic-item slug |
| `UNLOCKS_MOUNT` | `:Upgrade` -> `:Unit` | Mount option unlocked (parsed from armyListEntry links) |
| `REPLACES_WEAPON` | `:Upgrade` -> `:Weapon` | Weapon replaced (target = new weapon) |

### Army-list composition relationships

| Relationship | From -> To | Properties | Notes |
|---|---|---|---|
| `HAS_LIST` | `:Army` -> `:CompositionList` | — | parsed |
| `HAS_SLOT` | `:CompositionList` -> `:CompositionSlot` | — | parsed |
| `SLOT_ALLOWS` | `:CompositionSlot` -> `:Unit` | `max_count`, `per_points` | parsed |
| `ALLIED_WITH` | `:Army` -> `:Army` | `alliance_type` | parsed; `alliance_type` ∈ {"trusted","uneasy","suspicious"}. Not necessarily bidirectional. |

### Terrain interaction relationships

| Relationship | From -> To | Properties | Description |
|---|---|---|---|
| `TERRAIN_INTERACTION` | `:SpecialRule` -> `:Terrain` | `effect: String` | This special rule changes how a unit interacts with this terrain |
| `TERRAIN_INTERACTION` | `:TroopType` -> `:Terrain` | `effect: String` | This troop type has a special interaction with terrain |
| `HAS_INTRINSIC_RULE` | `:TroopType` -> `:SpecialRule` | — | Rule inherent to this troop type |

**`effect` vocabulary:** `ignores`, `ignores_cover`, `ignores_dangerous_test`,
`ignores_disruption`, `can_deploy_in`, `move_through_freely`, `cannot_enter`.

### Semantic relationships (extracted from hyperlinks in rule text)

| Relationship | From -> To | Description |
|---|---|---|
| `REFERENCES` | `:SpecialRule` -> `:SpecialRule` | Rule mentions another rule |
| `REFERENCES` | `:SpecialRule` -> `:CoreRule` | Rule references a core mechanic |
| `REFERENCES` | `:CoreRule` -> `:CoreRule` | Core mechanic references another |
| `REFERENCES` | `:CoreRule` -> `:SpecialRule` | Core mechanic references a special rule |
| `REFERENCES` | `:Spell` -> `:SpecialRule` | Spell references a special rule |
| `REFERENCES` | `:Spell` -> `:CoreRule` | Spell references a core mechanic |
| `REFERENCES` | `:MagicItem` -> `:SpecialRule` | Magic item confers or references a rule |

### Clarification and correction relationships

| Relationship | From -> To | Description |
|---|---|---|
| `CLARIFIES` | `:FAQ` -> `:SpecialRule` | FAQ clarifies a special rule |
| `CLARIFIES` | `:FAQ` -> `:CoreRule` | FAQ clarifies a core mechanic |
| `CLARIFIES` | `:FAQ` -> `:Unit` | FAQ clarifies a unit's profile or behaviour |
| `CLARIFIES` | `:FAQ` -> `:Spell` | FAQ clarifies a spell |
| `CLARIFIES` | `:FAQ` -> `:Weapon` | FAQ clarifies a weapon's profile or usage |
| `CLARIFIES` | `:FAQ` -> `:Terrain` | FAQ clarifies a terrain interaction |
| `AMENDS` | `:Errata` -> `:SpecialRule` | Errata corrects a special rule |
| `AMENDS` | `:Errata` -> `:CoreRule` | Errata corrects a core mechanic |
| `AMENDS` | `:Errata` -> `:Unit` | Errata modifies a unit's profile or equipment |
| `AMENDS` | `:Errata` -> `:Weapon` | Errata modifies a weapon's profile |
| `AMENDS` | `:Errata` -> `:Spell` | Errata modifies a spell |
| `AMENDS` | `:Errata` -> `:MagicItem` | Errata modifies a magic item |
| `AMENDS` | `:Errata` -> `:Terrain` | Errata modifies a terrain rule |

---

## Relationship diagram

```
  :FAQ / :Errata ── CLARIFIES / AMENDS ──────────────────────────────────────┐
                                                                               │
  :Army ──BELONGS_TO◄── :Unit ──HAS_RULE──────────────────► :SpecialRule ◄──────────┤
    │   HAS_LIST        │       │ HAS_PROFILE → :Profile                         │
    │       ▼           │       │ HAS_WEAPON ──► :Weapon (armour_value, ...      │
    │ :CompositionList  │       │ HAS_UPGRADE ▼ :Upgrade                         │
    │   HAS_SLOT         │       │   ├─UNLOCKS_RULE──► :SpecialRule              │
    │     ▼             │       │   ├─UNLOCKS_WEAPON► :Weapon  (relabelled)      │
    │ :CompositionSlot  │       │   ├─UNLOCKS_ITEM──► :MagicItem  (relabelled)   │
    │   SLOT_ALLOWS──►:Unit     │   ├─UNLOCKS_MOUNT► :Unit (mount)               │
    │                   │       │   └─REPLACES_WEAPON► :Weapon                   │
    │  ALLIED_WITH      │       │ CAN_TAKE_ITEM ► :MagicItem  (derived post-load) │
    ▼                   │       │ USES_LORE──► :Lore ◄─BELONGS_TO_LORE─ :Spell    │
  :Army                 │       │ CAN_MOUNT──► :Unit (mounts)                    │
                        │       └ SPLIT_PROFILE_OF──► :Unit (parent)             │
   :TroopType ◄─HAS_TYPE─┘                                                     │
        │  HAS_INTRINSIC_RULE──► :SpecialRule ──TERRAIN_INTERACTION──► :Terrain  │
        └─ TERRAIN_INTERACTION──► :Terrain                                     │
   :CoreRule ──PART_OF_SECTION──► :CoreRule   REFERENCES within/between rules ───┘
```

---

## Neo4j implementation notes

### Constraints and indexes

Authoritative source: `pipeline/graph/ddl.py` (`apply_constraints_and_indexes()`,
idempotent `IF NOT EXISTS`). Vector indexes are created separately in
`pipeline/embeddings/vector_store.py` after embeddings exist.

```cypher
-- Uniqueness constraints (one per label)
CREATE CONSTRAINT army_id        IF NOT EXISTS FOR (n:Army)            REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT unit_id        IF NOT EXISTS FOR (n:Unit)            REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT profile_id     IF NOT EXISTS FOR (n:Profile)         REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT special_rule_id IF NOT EXISTS FOR (n:SpecialRule)    REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT corerule_id    IF NOT EXISTS FOR (n:CoreRule)        REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT document_id    IF NOT EXISTS FOR (n:Document)        REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT trooptype_id   IF NOT EXISTS FOR (n:TroopType)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT terrain_id     IF NOT EXISTS FOR (n:Terrain)         REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT lore_id        IF NOT EXISTS FOR (n:Lore)            REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT spell_id       IF NOT EXISTS FOR (n:Spell)           REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT weapon_id      IF NOT EXISTS FOR (n:Weapon)          REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT magicitem_id   IF NOT EXISTS FOR (n:MagicItem)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT upgrade_id     IF NOT EXISTS FOR (n:Upgrade)         REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT complist_id    IF NOT EXISTS FOR (n:CompositionList) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT compslot_id    IF NOT EXISTS FOR (n:CompositionSlot) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT faq_id         IF NOT EXISTS FOR (n:FAQ)             REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT errata_id      IF NOT EXISTS FOR (n:Errata)          REQUIRE n.id IS UNIQUE;

-- B-tree indexes
CREATE INDEX unit_url        IF NOT EXISTS FOR (n:Unit)        ON (n.url);
CREATE INDEX special_rule_url IF NOT EXISTS FOR (n:SpecialRule) ON (n.url);
CREATE INDEX spell_url       IF NOT EXISTS FOR (n:Spell)       ON (n.url);
CREATE INDEX terrain_class   IF NOT EXISTS FOR (n:Terrain)     ON (n.terrain_class);
CREATE INDEX unit_troop_type IF NOT EXISTS FOR (n:Unit)        ON (n.troop_type_id);
CREATE INDEX corerule_url    IF NOT EXISTS FOR (n:CoreRule)    ON (n.url);
CREATE INDEX document_url    IF NOT EXISTS FOR (n:Document)    ON (n.url);
CREATE INDEX profile_order   IF NOT EXISTS FOR (n:Profile)     ON (n.order);
CREATE INDEX profile_name    IF NOT EXISTS FOR (n:Profile)     ON (n.name);
CREATE INDEX upgrade_type    IF NOT EXISTS FOR (n:Upgrade)     ON (n.upgrade_type);
CREATE INDEX upgrade_profile IF NOT EXISTS FOR (n:Upgrade)     ON (n.applies_to_profile);
CREATE INDEX upgrade_mutex   IF NOT EXISTS FOR (n:Upgrade)     ON (n.mutex_group);
```

### TroopType seed data

```python
# Source: tow.whfb.app/troop-types-at-a-glance/troop-type-table (Rulebook p.105)
TROOP_TYPE_SEED = [
    {"id": "regular-infantry",  "category": "Infantry",    "min_models_for_rank_bonus": 5,    "max_rank_bonus": 2, "unit_strength_per_model": "1"},
    {"id": "heavy-infantry",    "category": "Infantry",    "min_models_for_rank_bonus": 4,    "max_rank_bonus": 2, "unit_strength_per_model": "1"},
    {"id": "monstrous-infantry","category": "Infantry",    "min_models_for_rank_bonus": 3,    "max_rank_bonus": 2, "unit_strength_per_model": "3"},
    {"id": "swarms",            "category": "Infantry",    "min_models_for_rank_bonus": None, "max_rank_bonus": None, "unit_strength_per_model": "3"},
    {"id": "light-cavalry",     "category": "Cavalry",     "min_models_for_rank_bonus": 5,    "max_rank_bonus": 1, "unit_strength_per_model": "2"},
    {"id": "heavy-cavalry",     "category": "Cavalry",     "min_models_for_rank_bonus": 4,    "max_rank_bonus": 1, "unit_strength_per_model": "2"},
    {"id": "monstrous-cavalry", "category": "Cavalry",     "min_models_for_rank_bonus": 3,    "max_rank_bonus": 1, "unit_strength_per_model": "3"},
    {"id": "war-beasts",        "category": "War Beasts",  "min_models_for_rank_bonus": 5,    "max_rank_bonus": 1, "unit_strength_per_model": "1"},
    {"id": "light-chariots",    "category": "Chariots",    "min_models_for_rank_bonus": 3,    "max_rank_bonus": 1, "unit_strength_per_model": "3"},
    {"id": "heavy-chariots",    "category": "Chariots",    "min_models_for_rank_bonus": None, "max_rank_bonus": None, "unit_strength_per_model": "5"},
    {"id": "monstrous-creatures","category": "Monsters",   "min_models_for_rank_bonus": None, "max_rank_bonus": None, "unit_strength_per_model": "As Starting Wounds"},
    {"id": "behemoths",         "category": "Monsters",    "min_models_for_rank_bonus": None, "max_rank_bonus": None, "unit_strength_per_model": "As Starting Wounds"},
    {"id": "war-machines",      "category": "War Machines","min_models_for_rank_bonus": None, "max_rank_bonus": None, "unit_strength_per_model": "As Starting Wounds"},
]
```

### Weapon seed data for armour items

```python
# Source: tow.whfb.app/weapons-of-war/armour
ARMOUR_WEAPON_SEED = [
    {"id": "light-armour",     "weapon_class": "armour",    "armour_value": "5+",  "special_rules": []},
    {"id": "heavy-armour",     "weapon_class": "armour",    "armour_value": "4+",  "special_rules": []},
    {"id": "full-plate-armour","weapon_class": "armour",    "armour_value": "3+",  "special_rules": []},
    {"id": "shield",           "weapon_class": "equipment", "armour_value": "+1",  "special_rules": []},
    {"id": "barding",          "weapon_class": "equipment", "armour_value": "+1",  "special_rules": []},
]
```

### Vector indexes (per-label HNSW, ADR-0005 §6)

One HNSW vector index per embeddable label, named `<snake_label>_embedding_idx` (e.g.
`unit_embedding_idx`, `special_rule_embedding_idx`). Created by
`pipeline/embeddings/vector_store.py` after at least one embedding exists on each label.
Dimensions: 768. Similarity: cosine. Embeddable labels (`EMBEDDABLE_LABELS`):
`Army`, `Unit`, `SpecialRule`, `CoreRule`, `Document`, `TroopType`, `Spell`, `MagicItem`,
`Lore`, `Weapon`, `FAQ`, `Errata`, `Terrain`. `:Profile`, `:CompositionList`, and
`:CompositionSlot` are **not** embedded independently.

```cypher
CALL db.index.vector.queryNodes('unit_embedding_idx', 10, $queryVec)
YIELD node, score
RETURN node.name, score
```

### Key query examples

```cypher
// Stat filter across profiles (ADR-0005 §3)
MATCH (u:Unit)-[:HAS_PROFILE]->(p:Profile) WHERE p.WS >= 5 AND p.A >= 3
RETURN u.name, p.name, p.WS, p.A ORDER BY u.name;

// Rank-bonus rules and unit strength for Heavy Cavalry
MATCH (t:TroopType {id: "heavy-cavalry"})
RETURN t.min_models_for_rank_bonus, t.max_rank_bonus, t.unit_strength_per_model;

// Can Blood Knights charge through woods (any immunity)?
MATCH (u:Unit {id: "blood-knights"})-[:HAS_RULE]->(r:SpecialRule)-[e:TERRAIN_INTERACTION]->(t:Terrain {id: "woods"})
RETURN r.name, e.effect
UNION
MATCH (u:Unit {id: "blood-knights"})-[:HAS_TYPE]->(tt:TroopType)-[e:TERRAIN_INTERACTION]->(t:Terrain {id: "woods"})
RETURN tt.name, e.effect;

// Which armies can Vampire Counts ally with?
MATCH (vc:Army {id: "vampire-counts"})-[e:ALLIED_WITH]->(ally:Army)
RETURN ally.name AS ally_army, e.alliance_type ORDER BY e.alliance_type;

// Army composition slots for Vampire Counts
MATCH (a:Army {id: "vampire-counts"})-[:HAS_LIST]->(cl:CompositionList)-[:HAS_SLOT]->(cs:CompositionSlot)
RETURN cs.slot_name, cs.min_pct, cs.max_pct ORDER BY cs.slot_name;
```

### Creating nodes (Python neo4j-driver, flattened shape)

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

def create_unit(tx, row: dict):
    tx.run(
        """
        MERGE (u:Unit {id: $id})
        SET u += {
            url: $url, source_citation_book: $source_citation_book,
            source_citation_page: $source_citation_page, last_updated: $last_updated,
            cost_points_per_model: $cost_points_per_model, unit_category: $unit_category,
            troop_type_id: $troop_type_id, army_category: $army_category,
            base_width_mm: $base_width_mm, base_depth_mm: $base_depth_mm,
            unit_size_min: $unit_size_min, unit_size_max: $unit_size_max,
            is_named_character: $is_named_character, wizard_level: $wizard_level,
            av_intrinsic: $av_intrinsic, name: $name
        }
        """,
        **row,
    )

# Stat profiles are loaded separately as :Profile nodes + HAS_PROFILE edges;
# the loader is a pure MERGE that sets scalar columns directly from each parsed row.
```

### Embedding generation

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")

# Embedding text is built AFTER the graph is loaded, by querying each node's
# neighbours for graph context (per-label builders in pipeline/embeddings/text.py).
# English fields only — no i18n dict. One 768-d vector written to n.embedding.
# Resumable: MATCH (n:Label) WHERE n.embedding IS NULL ... makes re-runs skip done nodes.
```

---

*End of schema v3.1*
