# Knowledge Graph Schema
## Conversational Assistant System — Warhammer: The Old World
**Version:** 1.0  
**Data source:** tow.whfb.app  
**Last revised:** 2025-02-19

---

## Table of Contents
1. [Design principles](#design-principles)
2. [System constants](#system-constants)
3. [Node types](#node-types)
4. [Edge types](#edge-types)
5. [Relationship diagram](#relationship-diagram)
6. [Implementation notes](#implementation-notes)

---

## Design principles

- **English as the canonical language.** All structural data and source texts are stored in English. Translations are added in the `i18n` field of each node without modifying the graph structure.
- **`i18n` only for translatable fields.** Invariant fields (`id`, `url`, `source_citation`, numeric stats, dates) are never duplicated inside `i18n`.
- **Multilingual embeddings.** The system uses a multilingual embedding model (e.g. `paraphrase-multilingual-mpnet-base-v2`) that allows queries in any language without needing to translate the query at runtime.
- **Characteristic relationships as constants.** The mapping between profile abbreviations (`WS`, `BS`...) and their `CoreRule` nodes is resolved via a constants table (`CHARACTERISTIC_MAP`), not via graph edges, to avoid structural noise.
- **Controlled redundancy.** The `troop_type_id` and `unit_category_id` fields are stored as attributes on the `Unit` node in addition to existing as `HAS_TYPE` edges, to facilitate serialisation to the vector store without graph traversal.

---

## System constants

```python
# Map from profile abbreviations to CoreRule node ids
CHARACTERISTIC_MAP: dict[str, dict[str, str]] = {
    "M":  {"id": "movement",        "url": "https://tow.whfb.app/model-profiles/movement"},
    "WS": {"id": "weapon-skill",    "url": "https://tow.whfb.app/model-profiles/weapon-skill"},
    "BS": {"id": "ballistic-skill", "url": "https://tow.whfb.app/model-profiles/ballistic-skill"},
    "S":  {"id": "strength",        "url": "https://tow.whfb.app/model-profiles/strength"},
    "T":  {"id": "toughness",       "url": "https://tow.whfb.app/model-profiles/toughness"},
    "W":  {"id": "wounds",          "url": "https://tow.whfb.app/model-profiles/wounds"},
    "I":  {"id": "initiative",      "url": "https://tow.whfb.app/model-profiles/initiative"},
    "A":  {"id": "attacks",         "url": "https://tow.whfb.app/model-profiles/attacks"},
    "Ld": {"id": "leadership",      "url": "https://tow.whfb.app/model-profiles/leadership"},
}

# Supported languages
SUPPORTED_LANGUAGES: list[str] = ["en", "es"]
DEFAULT_LANGUAGE: str = "en"
```

---

## Node types

### `Army`
Represents each playable faction. Root node from which all units hang.

```python
{
    # --- Invariants ---
    "id":               str,    # unique slug. E.g: "vampire-counts"
    "url":              str,    # "https://tow.whfb.app/army/vampire-counts"
    "source_citation": {
        "book":         str,    # "Vampire Counts"
        "page":         int | None
    },
    "last_updated":     str,    # ISO 8601: "2024-03-01"

    # --- English canonical ---
    "name":             str,    # "Vampire Counts"

    # --- Translations ---
    "i18n": {
        "en": {"name": str},
        "es": {"name": str},
        # extensible: "fr", "de", ...
    }
}
```

---

### `Unit`
Represents units, characters and mounts with a stat profile.

```python
{
    # --- Invariants ---
    "id":               str,    # unique slug. E.g: "blood-knights"
    "url":              str,    # "https://tow.whfb.app/unit/blood-knights"
    "source_citation": {
        "book":         str,    # "Vampire Counts"
        "page":         int | None
    },
    "last_updated":     str,    # ISO 8601: "2024-03-01"

    "cost_points_per_model": int,   # 39 (always per model; unique characters have unit_size.max=1)

    "unit_category_id": str,    # TroopType node slug. E.g: "cavalry"
    "troop_type_id":    str,    # TroopType node slug. E.g: "heavy-cavalry"

    "base_size_mm": {
        "width":        int,    # front-facing dimension in mm. E.g: 30
        "depth":        int     # depth dimension in mm. E.g: 60
    },

    "unit_size": {
        "min":          int,    # minimum number of models. E.g: 5
        "max":          int | None  # None = no explicit maximum; 1 for unique characters/monsters
    },

    # List of sub-profiles (may be 1 or more if the unit has rider+mount, champion, etc.)
    # Stat keys are the canonical game abbreviations.
    # None represents "-" in the wiki (characteristic not applicable to that sub-profile).
    "profiles": [
        {
            "name": str,        # "Blood Knight", "Kastellan", "Nightmare"...
            "M":    int | None,
            "WS":   int | None,
            "BS":   int | None,
            "S":    int | None,
            "T":    int | None,
            "W":    int | None,
            "I":    int | None,
            "A":    int | None,
            "Ld":   int | None,
        }
    ],

    # --- English canonical ---
    "name":             str,    # "Blood Knights"

    # --- Translations ---
    "i18n": {
        "en": {"name": str},
        "es": {"name": str},
    }
}
```

> **Note on `profiles`:** The name of each sub-profile (`"name"`) is invariant (proper game name). Numeric values are invariant. There is no `text` field on `Unit` because a unit's textual content is distributed across the `Rule`, `Weapon` and `MagicItem` nodes linked by edges.

---

### `Rule`
Represents special rules: universal, army-specific, or unit-unique.

```python
{
    # --- Invariants ---
    "id":               str,    # slug. E.g: "necromantic-undead", "fear"
    "url":              str,    # "https://tow.whfb.app/special-rules/fear"
    "source_citation": {
        "book":         str,    # "Rulebook" or "Vampire Counts"
        "page":         int | None
    },
    "last_updated":     str,    # ISO 8601

    # Rule scope:
    # "universal" → applies to all armies
    # "army"      → specific to one army (army_id required)
    # "unique"    → specific to a single unit
    "rule_scope":       str,    # "universal" | "army" | "unique"
    "army_id":          str | None,  # army slug if rule_scope = "army"

    # --- English canonical ---
    "name":             str,    # "Fear"
    "text":             str,    # full rule text in English

    # --- Translations ---
    "i18n": {
        "en": {"name": str, "text": str},
        "es": {"name": str, "text": str},
    }
}
```

---

### `CoreRule`
Represents pages covering general rulebook mechanics (game phases, movement, shooting, magic, profiles, terrain, etc.). Distinguished from `Rule` in that it is not a special rule owned by a unit, but a system mechanic.

```python
{
    # --- Invariants ---
    "id":               str,    # slug. E.g: "the-charge-move"
    "url":              str,    # "https://tow.whfb.app/movement-in-detail/the-charge-move"
    "source_citation": {
        "book":         str,    # "Rulebook"
        "page":         int | None
    },
    "last_updated":     str,    # ISO 8601

    "section":          str,    # parent section name in the wiki. E.g: "Movement in Detail"
    "section_id":       str,    # parent section slug. E.g: "movement-in-detail"

    # Sequential navigation (useful for retrieval context)
    "prev_page_url":    str | None,
    "next_page_url":    str | None,

    # --- English canonical ---
    "name":             str,    # "The Charge Move"
    "text":             str,    # full text

    # --- Translations ---
    "i18n": {
        "en": {"name": str, "text": str},
        "es": {"name": str, "text": str},
    }
}
```

---

### `TroopType`
Represents troop types and subtypes from the rulebook. Nodes exist in the wiki under `/troop-types-in-detail/`.

```python
{
    # --- Invariants ---
    "id":               str,    # slug. E.g: "heavy-cavalry"
    "url":              str,    # "https://tow.whfb.app/troop-types-in-detail/heavy-cavalry"
    "source_citation": {
        "book":         str,
        "page":         int | None
    },
    "last_updated":     str,

    "category":         str,    # top-level category. E.g: "cavalry", "infantry", "monster"

    # --- English canonical ---
    "name":             str,    # "Heavy Cavalry"
    "text":             str,    # troop type description

    # --- Translations ---
    "i18n": {
        "en": {"name": str, "text": str},
        "es": {"name": str, "text": str},
    }
}
```

---

### `Weapon`
Represents weapons, armour and additional equipment.

```python
{
    # --- Invariants ---
    "id":               str,    # slug. E.g: "lance"
    "url":              str,    # "https://tow.whfb.app/weapons-of-war/lance"
    "source_citation": {
        "book":         str,
        "page":         int | None
    },
    "last_updated":     str,

    # Equipment classification
    "weapon_class":     str,    # "melee" | "missile" | "armour" | "equipment"

    # --- English canonical ---
    "name":             str,    # "Lance"
    "text":             str,    # full description including rules of use

    # --- Translations ---
    "i18n": {
        "en": {"name": str, "text": str},
        "es": {"name": str, "text": str},
    }
}
```

---

### `Spell`
Represents individual spells from the Lores of Magic.

```python
{
    # --- Invariants ---
    "id":               str,    # slug. E.g: "invocation-of-nehek"
    "url":              str,    # lore page URL (with anchor to the spell if applicable)
    "source_citation": {
        "book":         str,
        "page":         int | None
    },
    "last_updated":     str,

    "lore_id":          str,    # lore slug. E.g: "necromancy"
    "casting_value":    int,    # casting value
    "spell_type":       str,    # "Hex" | "Magic Missile" | "Conveyance" | "Enchantment" |
                                # "Assailment" | "Magical Vortex" | "Bound Spell"

    # --- English canonical ---
    "name":             str,    # "Invocation of Nehek"
    "text":             str,    # full spell text

    # --- Translations ---
    "i18n": {
        "en": {"name": str, "text": str},
        "es": {"name": str, "text": str},
    }
}
```

---

### `MagicItem`
Represents universal magic items and army-specific powers (e.g. Vampiric Powers).

```python
{
    # --- Invariants ---
    "id":               str,    # slug. E.g: "sword-of-battle"
    "url":              str,    # "https://tow.whfb.app/magic-items/magic-weapons"
    "source_citation": {
        "book":         str,
        "page":         int | None
    },
    "last_updated":     str,

    "item_type":        str,    # "magic_weapon" | "magic_armour" | "talisman" |
                                # "magic_standard" | "enchanted_item" | "arcane_item" |
                                # "vampiric_power" | (other army-specific powers)
    "points_cost":      int | None,  # points cost; None if variable
    "army_id":          str | None,  # None if universal; army slug if exclusive to one army

    # --- English canonical ---
    "name":             str,
    "text":             str,    # full description including in-game effects

    # --- Translations ---
    "i18n": {
        "en": {"name": str, "text": str},
        "es": {"name": str, "text": str},
    }
}
```

---

### `FAQ`
Represents official FAQ entries integrated in the wiki.

```python
{
    # --- Invariants ---
    "id":               str,    # generated slug. E.g: "faq-regeneration-flaming-attacks"
    "url":              str,    # "https://tow.whfb.app/faq" (with anchor if applicable)
    "source_citation": {
        "book":         str,    # "FAQ 2024"
        "page":         int | None
    },
    "last_updated":     str,

    # --- English canonical ---
    "question":         str,    # question text
    "answer":           str,    # answer text

    # --- Translations ---
    "i18n": {
        "en": {"question": str, "answer": str},
        "es": {"question": str, "answer": str},
    }
}
```

---

### `Errata`
Represents official corrections and amendments integrated in the wiki.

```python
{
    # --- Invariants ---
    "id":               str,    # generated slug. E.g: "errata-regeneration-2024-01"
    "url":              str,    # "https://tow.whfb.app/errata"
    "source_citation": {
        "book":         str,    # "Errata & Amendments 2024"
        "page":         int | None
    },
    "last_updated":     str,

    # --- English canonical ---
    "original_text":    str,    # original text being corrected
    "corrected_text":   str,    # correct text after the amendment

    # --- Translations ---
    "i18n": {
        "en": {"original_text": str, "corrected_text": str},
        "es": {"original_text": str, "corrected_text": str},
    }
}
```

---

## Edge types

All edges are **directed**. The graph is implemented as `networkx.DiGraph`.

### Structural relationships

| Edge | From → To | Description | Example |
|---|---|---|---|
| `BELONGS_TO` | `Unit` → `Army` | Unit belongs to an army | Blood Knights → Vampire Counts |
| `HAS_TYPE` | `Unit` → `TroopType` | Troop type of the unit | Blood Knights → Heavy Cavalry |
| `HAS_RULE` | `Unit` → `Rule` | Base special rule of the unit (always active) | Blood Knights → Regeneration |
| `HAS_OPTIONAL_RULE` | `Unit` → `Rule` | Rule acquirable as a points upgrade | Blood Knights → Drilled |
| `HAS_WEAPON` | `Unit` → `Weapon` | Standard equipment included in base cost | Blood Knights → Lance |
| `HAS_OPTIONAL_WEAPON` | `Unit` → `Weapon` | Optional or replaceable equipment | Vampire Count → Great Weapon |
| `CAN_MOUNT` | `Unit` → `Unit` | Character can ride this mount | Vampire Count → Zombie Dragon |
| `CAN_TAKE_ITEM` | `Unit` → `MagicItem` | Can purchase items of this category | Vampire Count → Vampiric Powers |
| `USES_LORE` | `Unit` → `Spell` | Wizard can use spells from this lore | Vampire Count → Necromancy |
| `PART_OF_SECTION` | `CoreRule` → `CoreRule` | Hierarchical parent-child section relationship | The Charge Move → Movement in Detail |

### Edge attributes for upgrades

Edges representing points upgrades carry a `cost` attribute:

```python
# Example: Blood Knights can acquire Drilled for +3 pts/model
graph.add_edge("blood-knights", "drilled",
    relation="HAS_OPTIONAL_RULE",
    cost=3,
    cost_unit="per_model"   # "per_model" | "per_unit" | "fixed"
)
```

### Semantic relationships (extracted from hyperlinks in text)

| Edge | From → To | Description | Extraction source |
|---|---|---|---|
| `REFERENCES` | `Rule` → `Rule` | Rule mentions or cites another rule | Links in body text |
| `REFERENCES` | `Rule` → `CoreRule` | Rule cites a rulebook mechanic | Links in body text |
| `REFERENCES` | `CoreRule` → `CoreRule` | Mechanic cites another mechanic | Links in body text |
| `REFERENCES` | `CoreRule` → `Rule` | Mechanic cites a special rule | Links in body text |
| `REFERENCES` | `Spell` → `Rule` | Spell cites a special rule | Links in body text |
| `REFERENCES` | `Spell` → `CoreRule` | Spell cites a mechanic | Links in body text |

### Clarification and correction relationships

| Edge | From → To | Description |
|---|---|---|
| `CLARIFIES` | `FAQ` → `Rule` | FAQ clarifies a special rule |
| `CLARIFIES` | `FAQ` → `CoreRule` | FAQ clarifies a rulebook mechanic |
| `CLARIFIES` | `FAQ` → `Unit` | FAQ clarifies a unit's profile or behaviour |
| `AMENDS` | `Errata` → `Rule` | Errata corrects the text of a special rule |
| `AMENDS` | `Errata` → `CoreRule` | Errata corrects a rulebook mechanic |
| `AMENDS` | `Errata` → `Unit` | Errata modifies a unit's profile or equipment |

---

## Relationship diagram

```
                    CLARIFIES / AMENDS
  FAQ / Errata ──────────────────────────────────────────┐
                                                         │
  Army ◄──── BELONGS_TO ───── Unit ─── HAS_RULE ────────► Rule
                               │                          │
                               │ HAS_WEAPON               │ REFERENCES
                               ▼                          ▼
                             Weapon              CoreRule ◄──────┐
                               │                    │            │
                               │      REFERENCES    │   PART_OF  │
                               │         ┌──────────┘   SECTION  │
                               │         ▼                        │
                               │    CoreRule ─────────────────────┘
                               │
                   CAN_MOUNT ──┴──► Unit (mounts)
                               │
                  USES_LORE ───┴──► Spell
                               │
              CAN_TAKE_ITEM ───┴──► MagicItem
                               │
                  HAS_TYPE ────┴──► TroopType
```

---

## Implementation notes

### Graph serialisation

NetworkX serialises the graph to GraphML or JSON. Attributes must be primitive types or JSON strings for compatibility:

```python
import json
import networkx as nx

G = nx.DiGraph()

# Compound attributes (dicts, lists) are serialised as JSON strings
node_data = {
    "id": "blood-knights",
    "source_citation": json.dumps({"book": "Vampire Counts", "page": 13}),
    "profiles": json.dumps([{"name": "Blood Knight", "WS": 5, ...}]),
    "base_size_mm": json.dumps({"width": 30, "depth": 60}),
    "i18n": json.dumps({"en": {"name": "Blood Knights"}, "es": {"name": "Caballeros de Sangre"}}),
    # Primitives directly:
    "cost_points_per_model": 39,
    "last_updated": "2024-03-01",
    "name": "Blood Knights",
}
G.add_node("blood-knights", **node_data)
```

### Generating embeddings

One embedding is generated per node using the `text` field (or `question`+`answer` for FAQ nodes):

```python
# With multilingual models, texts in different languages
# are projected into the same vector space:
# → a query in Spanish finds nodes whose text is in English

from sentence_transformers import SentenceTransformer

model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")

for node_id, data in G.nodes(data=True):
    text_en = data.get("text", data.get("name", ""))
    embedding = model.encode(text_en)
    # Store in vector store (ChromaDB / FAISS) with node metadata
```

### Adding a new language

The process does not modify the graph structure:

```python
def add_language(G: nx.DiGraph, lang_code: str, translation_fn) -> None:
    """Add translations to all nodes without modifying the graph structure."""
    for node_id, data in G.nodes(data=True):
        i18n = json.loads(data.get("i18n", "{}"))
        if lang_code not in i18n:
            translatable = {
                "name": data.get("name", ""),
                "text": data.get("text", ""),
            }
            i18n[lang_code] = translation_fn(translatable, target_lang=lang_code)
            G.nodes[node_id]["i18n"] = json.dumps(i18n)
```

### Language fallback

At query time, if the requested language is not available, English is used as fallback:

```python
def get_text(node_data: dict, lang: str, field: str = "text") -> str:
    i18n = json.loads(node_data.get("i18n", "{}"))
    if lang in i18n and field in i18n[lang]:
        return i18n[lang][field]
    return node_data.get(field, "")  # fallback to English canonical
```# Knowledge Graph Schema
## Conversational Assistance System — Warhammer: The Old World
**Version:** 3.0
**Graph database:** Neo4j
**Data source:** tow.whfb.app
**Last revised:** 2026-02-20
**Supersedes:** Version 2.0

---

## Changelog — v2.0 → v3.0

This version is driven by a full re-analysis of the wiki against the two main system
objectives: (1) complex multi-rule query resolution, and (2) army list building assistance.
Nine structural gaps were identified and corrected.

| # | Gap | Impact on Objectives |
|---|-----|----------------------|
| 1 | `:TroopType` missing `min_models_for_rank_bonus`, `max_rank_bonus`, `unit_strength_per_model` | Rank bonus eligibility, outnumber checks (Obj 1, 2.3) |
| 2 | `:Weapon` missing `armour_value`, `shots`, `template_type`, `is_indirect`, `bounce` | AV calculation, war machine firing profiles (Obj 2.1, 2.5) |
| 3 | `:Unit` missing `av_intrinsic` | Durability of monsters / units with natural armour (Obj 2.1) |
| 4 | No `:Terrain` node existed | Terrain-unit interaction queries (Obj 1, 2.4) |
| 5 | No `ALLIED_WITH` relationship | Army pairing and contingent queries (Obj 2.2) |
| 6 | `:Upgrade` missing `magic_standard_budget` | Standard bearer item budget constraints (Obj 2.7) |
| 7 | `:Army` missing structured `composition_percentages` | Army-building percentage queries (Obj 2.7) |
| 8 | No `TERRAIN_INTERACTION` edges | Multi-hop rule × terrain reasoning (Obj 1, 2.4) |
| 9 | `:FAQ`/`:Errata` CLARIFIES/AMENDS not extended to `:Terrain` | Terrain FAQ resolution (Obj 1) |

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
  English. Translations are added in the `i18n` map property of each node without modifying
  graph structure.
- **`i18n` only for translatable fields.** Invariant fields (`id`, `url`, `source_citation`,
  numeric stats, dates) are never duplicated inside `i18n`.
- **Multilingual embeddings.** The system uses a multilingual embedding model (e.g.
  `paraphrase-multilingual-mpnet-base-v2`) so queries in any language match nodes whose text
  is stored in English.
- **Characteristics as constants.** The mapping from profile abbreviations (`WS`, `BS`, …) to
  their `CoreRule` nodes is resolved via a `CHARACTERISTIC_MAP` constant in code, not as graph
  edges, to avoid structural noise.
- **Controlled redundancy.** `troop_type_id` and `unit_category` are stored both as `Unit`
  node properties *and* as `HAS_TYPE` edges, to enable serialisation to the vector store
  without graph traversal.
- **Neo4j native types.** Lists and maps are stored as native Neo4j property types (no JSON
  serialisation required). Node labels follow PascalCase; relationship types follow
  SCREAMING_SNAKE_CASE.
- **Uniqueness constraints on `id`.** Every node type has a uniqueness constraint on `id` and
  a B-tree index on `url`.
- **Terrain as first-class entities.** The seven terrain categories plus special features are
  modelled as `:Terrain` nodes (not buried as `:CoreRule` text) to enable direct graph
  traversal for unit-terrain interaction queries.
- **Alliance data as edges.** Army-to-army alliance relationships are modelled as directed
  `ALLIED_WITH` edges to support multi-hop questions such as "which armies can Vampire Counts
  ally with, and on what terms?"

---

## System constants

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

# Terrain category IDs — used in TERRAIN_INTERACTION edges
TERRAIN_CATEGORIES = [
    "open-ground", "difficult-terrain", "dangerous-terrain", "impassable-terrain",
    "low-linear-obstacle", "high-linear-obstacle", "woods", "hills",
    "special-feature", "building", "linear-terrain-feature",
]

SUPPORTED_LANGUAGES = ["en", "es"]
DEFAULT_LANGUAGE    = "en"
```

---

## Node types

Each node type corresponds to a **Neo4j label** (`:Army`, `:Unit`, etc.). Properties marked as
`map` or `list` are stored as native Neo4j map/list properties.

---

### `:Army`
Represents a playable faction. Root node from which all units hang.

```
Properties
----------
id               : String   -- unique slug. e.g. "vampire-counts"
url              : String   -- "https://tow.whfb.app/army/vampire-counts"
source_citation  : Map      -- {book: "Vampire Counts", page: null}
last_updated     : String   -- ISO 8601 date. e.g. "2024-03-01"
name             : String   -- "Vampire Counts"

# Structured composition percentages for the Grand Army list.        [NEW v3.0]
# Maps category -> {min_pct, max_pct}. null means no hard limit.
composition_percentages : Map -- {
    characters: {min_pct: null, max_pct: 50},
    core:       {min_pct: 25,   max_pct: null},
    special:    {min_pct: null, max_pct: 50},
    rare:       {min_pct: null, max_pct: 25},
    allies:     {min_pct: null, max_pct: 25}
}

i18n             : Map      -- {en: {name: "Vampire Counts"}, es: {name: "Condes Vampiro"}}
```

> **Composition rules detail.** Full composition text (including conditional rules such as
> "0-1 Blood Knights per 1,000 pts" and Army of Infamy lists) is captured as `CoreRule` nodes
> linked via `HAS_COMPOSITION_RULE`. The `composition_percentages` map captures only the
> universal percentage thresholds needed for structured army-building queries.
>
> **Ally relationships.** Each army's allowed allies (and their alliance type) are modelled as
> `ALLIED_WITH` edges: `(:Army)-[:ALLIED_WITH {alliance_type}]->(:Army)`.

---

### `:Unit`
Represents units, characters, and mounts with a stat profile.

```
Properties
----------
id                   : String      -- unique slug. e.g. "blood-knights"
url                  : String      -- "https://tow.whfb.app/unit/blood-knights"
source_citation      : Map         -- {book: "Vampire Counts", page: 13}
last_updated         : String      -- ISO 8601

cost_points_per_model: Integer     -- 39

# Denormalised for vector store serialisation (also encoded as HAS_TYPE edge)
unit_category        : String      -- broad category string. e.g. "Cavalry"
troop_type_id        : String      -- slug of the :TroopType node. e.g. "heavy-cavalry"

# Army list slot (source: /unit/{slug} page header)
army_category        : String|List<String>
                                   -- "Named Characters" | "Characters" | "Core" |
                                      "Special" | "Rare" | "Mounts"
                                      # List when unit appears in multiple slots.

base_size_mm         : Map         -- {width: 30, depth: 60}

unit_size            : Map         -- {min: 5, max: null}
                                      # null = no explicit upper limit
                                      # max: 1 for single models

is_named_character   : Boolean     -- false for generic units

# Intrinsic armour value (NEW in v3.0)
# For units whose armour comes from their nature, NOT purchasable equipment.
# Examples: monsters with scaly skin, ethereal units with unnatural resilience.
# Format: "5+", "4+", "3+" (save value as printed). null if AV is equipment-only.
av_intrinsic         : String|null -- null for most units

# Wizard properties (null if the unit is not a wizard by default)
wizard_level         : Integer|null -- 1 | 2 | 3 | 4 | null

# Stat profiles. A unit may have 1-N sub-profiles.
# null represents "-" in the wiki (characteristic not applicable).
profiles             : List<Map>   -- [
                           {
                             name : String,
                             M    : Integer|null,
                             WS   : Integer|null,
                             BS   : Integer|null,
                             S    : Integer|null,
                             T    : Integer|null,
                             W    : Integer|null,
                             I    : Integer|null,
                             A    : Integer|null,
                             Ld   : Integer|null
                           }
                         ]

name                 : String      -- "Blood Knights"
i18n                 : Map         -- {en: {name: "Blood Knights"}, es: {name: "..."}}
```

> **Notes:**
> - Split profiles (cavalry rider + mount, chariot + crew) are stored as separate entries
>   inside the same `profiles` list AND connected via `SPLIT_PROFILE_OF` edges.
> - AV (Armour Value) is NOT part of the M/WS/.../Ld profile. It is derived from equipment
>   and `av_intrinsic`. See the AV calculation recipe in implementation notes.
> - Wizard upgrade options (e.g. "Be a Level 1 Wizard +30 pts") are modelled as
>   `:Upgrade` nodes with `upgrade_type: "wizard_level"`.

---

### `:TroopType`
Represents the specific troop types defined in `/troop-types-in-detail/`.

```
Properties
----------
id               : String      -- slug. e.g. "heavy-cavalry"
url              : String      -- "https://tow.whfb.app/troop-types-in-detail/heavy-cavalry"
source_citation  : Map         -- {book: "Rulebook", page: null}
last_updated     : String

category         : String      -- "Infantry" | "Cavalry" | "War Beasts" | "Chariots" |
                                   "Monsters" | "War Machines" | "Swarms"

# === NEW in v3.0 (from Troop Type Table, Rulebook p.105) ====================
#
# min_models_for_rank_bonus: minimum models a rank must contain to count toward Rank Bonus.
#   null for types with no Rank Bonus (Heavy Chariots, Monsters, War Machines, Swarms).
min_models_for_rank_bonus : Integer|null

# max_rank_bonus: maximum Rank Bonus this troop type can claim.
#   null for types that get no Rank Bonus.
max_rank_bonus   : Integer|null

# unit_strength_per_model: unit strength value per individual model.
#   String because some types use "As Starting Wounds" rather than a fixed integer.
unit_strength_per_model : String  -- "1" | "2" | "3" | "5" | "As Starting Wounds"

# ============================================================================

name             : String      -- "Heavy Cavalry"
text             : String      -- full description of the troop type and its rules
i18n             : Map         -- {en: {name: "...", text: "..."}, es: {name: "...", text: "..."}}
```

> Each troop type carries intrinsic rules (e.g. Heavy Infantry -> "Steady in the Ranks",
> Monstrous Infantry -> "Clumsy"). These are captured as `HAS_INTRINSIC_RULE` edges.
>
> **Using these fields at query time (application layer, not graph data):**
> - Rank Bonus eligibility: a rank contributes Rank Bonus only if its model count ≥
>   `min_models_for_rank_bonus`. The graph stores the threshold; the application checks it.
> - Unit Strength of a given model count is computed as `count × unit_strength_per_model`
>   in application code. The graph stores the per-model multiplier, not a specific count.

---

### `:Rule`
Represents special rules: universal, army-specific, or unit-unique.

```
Properties
----------
id               : String      -- slug. e.g. "fear", "necromantic-undead"
url              : String      -- "https://tow.whfb.app/special-rules/fear"
source_citation  : Map         -- {book: "Rulebook", page: null}
last_updated     : String

rule_scope       : String      -- "universal" | "army" | "unique"
army_id          : String|null -- army slug if rule_scope = "army" or "unique"

name             : String      -- "Fear"
text             : String      -- full rule text
i18n             : Map         -- {en: {name: "...", text: "..."}, es: {name: "...", text: "..."}}
```

---

### `:CoreRule`
Represents pages covering core game mechanics (phases, movement, shooting, magic, army
composition, etc.). Distinct from `:Rule`: a `CoreRule` is a system mechanic, not a special
rule that a unit possesses.

```
Properties
----------
id               : String      -- slug. e.g. "the-charge-move"
url              : String      -- "https://tow.whfb.app/movement-in-detail/the-charge-move"
source_citation  : Map         -- {book: "Rulebook", page: null}
last_updated     : String

section          : String      -- parent section name. e.g. "Movement in Detail"
section_id       : String      -- parent section slug. e.g. "movement-in-detail"

prev_page_url    : String|null
next_page_url    : String|null

name             : String      -- "The Charge Move"
text             : String      -- full text
i18n             : Map         -- {en: {name: "...", text: "..."}, es: {name: "...", text: "..."}}
```

---

### `:Terrain`  *(NEW in v3.0)*
Represents a terrain category or specific terrain feature. First-class entity to enable
direct graph traversal for unit-terrain interaction queries (objective 2.4).

```
Properties
----------
id               : String   -- slug. e.g. "difficult-terrain", "woods", "tower"
url              : String   -- "https://tow.whfb.app/battlefield-terrain/difficult-terrain"
source_citation  : Map      -- {book: "Rulebook", page: null}
last_updated     : String

terrain_class    : String   -- "open" | "difficult" | "dangerous" | "impassable" |
                               "low_linear_obstacle" | "high_linear_obstacle" | "woods" |
                               "hills" | "special_feature" | "building" |
                               "linear_terrain_feature"

# Movement effects
movement_penalty : String|null -- description. e.g. "-1 to M (min 1)" for difficult terrain.
                                  null for terrain with no movement penalty.
blocks_movement  : Boolean     -- true for impassable terrain and high linear obstacles

# Combat effects
disrupts_units   : Boolean     -- true if a unit with 25%+ models inside becomes Disrupted
                                  (loses Rank Bonus). true for difficult terrain, woods.
requires_dangerous_test : Boolean -- true if models inside must make a Dangerous Terrain test
                                     (D6; roll of 1 = lose 1 Wound).

# Shooting effects
grants_cover     : String|null -- "partial" | "full" | null

# Special feature properties (only when terrain_class = "special_feature")
special_feature_benefit : String|null -- text of control benefit

name             : String   -- "Difficult Terrain"
text             : String   -- full rules text including all interactions
i18n             : Map      -- {en: {name: "...", text: "..."}, es: {name: "...", text: "..."}}
```

**Terrain node catalogue:**

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

### `:Lore`  *(added in v2.0)*
Represents a Lore of Magic.

```
Properties
----------
id               : String   -- slug. e.g. "necromancy", "battle-magic"
url              : String   -- "https://tow.whfb.app/the-lores-of-magic/necromancy"
source_citation  : Map      -- {book: "Rulebook", page: null}
last_updated     : String
name             : String   -- "Necromancy"
text             : String   -- lore description / flavour text
i18n             : Map      -- {en: {name: "...", text: "..."}, es: {name: "...", text: "..."}}
```

---

### `:Spell`
Represents individual spells within a Lore of Magic.

```
Properties
----------
id               : String      -- slug. e.g. "invocation-of-nehek"
url              : String
source_citation  : Map
last_updated     : String

lore_id          : String      -- slug of the parent :Lore node
lore_number      : Integer|null -- 0 = signature spell; 1-6 = numbered spells; null if N/A

casting_value         : Integer     -- base casting value
casting_value_boosted : Integer|null -- enhanced CV (null if N/A)

spell_type       : String      -- "Hex" | "Magic Missile" | "Conveyance" | "Enchantment" |
                                   "Assailment" | "Magical Vortex" | "Bound Spell"

range            : String      -- "Self" | "Combat" | "24" | ...
duration         : String      -- "Instant" | "Until end of turn" | "Remains in Play" | ...
target           : String      -- e.g. "enemy unit", "friendly unit", "self"

name             : String
text             : String      -- full spell text
i18n             : Map
```

---

### `:Weapon`
Represents weapons, armour, and additional equipment.

```
Properties
----------
id               : String      -- slug. e.g. "lance", "heavy-armour", "cannon"
url              : String
source_citation  : Map
last_updated     : String

weapon_class     : String      -- "melee" | "missile" | "armour" | "equipment" | "war_machine"

# --- Weapon combat/missile profile (melee and missile) ---------------------
range            : String|null -- "Combat" for melee; "24" for missile
strength         : String|null -- "S" | "S+2" | "4"
ap               : String|null -- e.g. "-1", "-2"; null if no AP modifier
special_rules    : List<String> -- rule slugs conferred by this weapon

# --- Armour / equipment profile (NEW in v3.0) ------------------------------
# For weapon_class = "armour" or "equipment". null for pure attack weapons.
armour_value     : String|null -- AV granted or modified.
                                  Absolute: "5+", "4+", "3+" (e.g. heavy armour = "4+")
                                  Relative: "+1" (e.g. shield, barding = "+1")
                                  null for non-armour items

# --- War machine firing profile (NEW in v3.0) ------------------------------
# For weapon_class = "war_machine". null for all other classes.
shots            : String|null -- "1" | "D3" | "3D6" | null
template_type    : String|null -- "blast" | "large_blast" | "flame_template" | null
is_indirect      : Boolean     -- true for stone throwers
bounce           : Boolean     -- true for cannon balls

name             : String
text             : String      -- full description including restrictions and notes
i18n             : Map
```

> **AV calculation recipe:**
> 1. Start from `unit.av_intrinsic` (if not null).
> 2. Override with the highest-tier armour item's absolute `armour_value`
>    (e.g. Full Plate Armour = "3+" beats Heavy Armour = "4+").
> 3. Apply all "+1" modifiers from shields, barding, etc.
> 4. Cap by troop type: infantry/cavalry max 2+; chariots/monsters/war machines max 3+.

---

### `:MagicItem`
Represents universal magic items and army-specific powers.

```
Properties
----------
id               : String      -- slug. e.g. "sword-of-battle", "dark-acolyte"
url              : String
source_citation  : Map
last_updated     : String

item_type        : String      -- "magic_weapon" | "magic_armour" | "talisman" |
                                   "magic_standard" | "enchanted_item" | "arcane_item" |
                                   "vampiric_power" | (other army-specific categories)

points_cost      : Integer|null -- null if variable or free
army_id          : String|null  -- null for universal items
is_single_use    : Boolean      -- true for items consumed on use

name             : String
text             : String      -- full description
i18n             : Map
```

---

### `:Upgrade`  *(added in v2.0)*
Represents a purchasable upgrade option for a unit.

```
Properties
----------
id               : String      -- slug. e.g. "blood-knights-champion"
url              : String      -- same as parent unit page
last_updated     : String

upgrade_type     : String      -- "command_champion" | "command_standard" | "command_musician" |
                                   "weapon_replace" | "weapon_add" | "rule_add" | "mount" |
                                   "wizard_level"

description      : String      -- short label. e.g. "Upgrade one model to a Kastellan"
points_cost      : Integer     -- absolute cost
cost_unit        : String      -- "per_model" | "per_unit" | "fixed"

# For command champion upgrades
champion_magic_allowance  : Integer|null -- max pts on magic items (e.g. 25 for Kastellan)
champion_power_allowance  : Integer|null -- max pts on army-specific powers

# For command standard bearer upgrades (NEW in v3.0)
magic_standard_budget     : Integer|null -- max pts this standard bearer may spend on
                                            a magic standard. e.g. 50 for a unit standard
                                            bearer, null for units whose standard bearer
                                            cannot take a magic standard.
                                            Note: the Battle Standard Bearer's upgrade node
                                            stores null here too — their unlimited magic
                                            standard budget is a BSB rule, not a property
                                            of the upgrade itself; see the BSB CoreRule.

# For weapon_replace upgrades
replaces_weapon_id : String|null -- slug of the weapon being replaced
```

---

### `:FAQ`
Represents official FAQ entries.

```
Properties
----------
id               : String   -- generated slug. e.g. "faq-rerolls-discarded"
url              : String
source_citation  : Map
last_updated     : String

topic            : String   -- wiki topic slug. e.g. "movement", "shooting"
source_version   : String   -- e.g. "1.5.2"
source_document  : String   -- "Official Warhammer: The Old World FAQ & Errata" |
                               "Official Forces of Fantasy FAQ & Errata" |
                               "Official Ravening Hordes FAQ & Errata"

question         : String
answer           : String
i18n             : Map
```

---

### `:Errata`
Represents corrections and amendments.

```
Properties
----------
id               : String
url              : String
source_citation  : Map
last_updated     : String

source_version   : String
source_document  : String -- same vocabulary as :FAQ

original_text    : String  -- text before amendment (null if additive)
corrected_text   : String
i18n             : Map
```

---

## Relationship types

### Structural relationships

| Relationship | From -> To | Description |
|---|---|---|
| `BELONGS_TO` | `:Unit` -> `:Army` | Unit belongs to a faction |
| `HAS_UNIT` | `:Army` -> `:Unit` | Faction includes this unit |
| `HAS_TYPE` | `:Unit` -> `:TroopType` | Troop type of the unit |
| `HAS_INTRINSIC_RULE` | `:TroopType` -> `:Rule` | Rule inherent to this troop type |
| `HAS_RULE` | `:Unit` -> `:Rule` | Always-active special rule |
| `HAS_WEAPON` | `:Unit` -> `:Weapon` | Standard equipment in base cost |
| `HAS_UPGRADE` | `:Unit` -> `:Upgrade` | Purchasable upgrade option |
| `UNLOCKS_WEAPON` | `:Upgrade` -> `:Weapon` | Weapon added by upgrade |
| `UNLOCKS_RULE` | `:Upgrade` -> `:Rule` | Rule added by upgrade |
| `UNLOCKS_ITEM` | `:Upgrade` -> `:MagicItem` | Item category unlocked |
| `REPLACES_WEAPON` | `:Upgrade` -> `:Weapon` | Weapon replaced (target = new weapon) |
| `CAN_MOUNT` | `:Unit` -> `:Unit` | Character can take this mount |
| `SPLIT_PROFILE_OF` | `:Unit` -> `:Unit` | Sub-unit belongs to parent (mount -> rider) |
| `CAN_TAKE_ITEM` | `:Unit` -> `:MagicItem` | Unit can purchase this item category |
| `USES_LORE` | `:Unit` -> `:Lore` | Wizard can generate spells from this lore |
| `BELONGS_TO_LORE` | `:Spell` -> `:Lore` | Spell is part of this lore |
| `PART_OF_SECTION` | `:CoreRule` -> `:CoreRule` | Child rule belongs to parent section |
| `HAS_COMPOSITION_RULE` | `:Army` -> `:CoreRule` | Army-specific composition page text |

---

### Alliance relationships  *(NEW in v3.0)*

| Relationship | From -> To | Properties | Description |
|---|---|---|---|
| `ALLIED_WITH` | `:Army` -> `:Army` | `alliance_type: "trusted" OR "uneasy" OR "suspicious"` | Main army may include an allied contingent from the target army. Not necessarily bidirectional — must be created per army's composition list. |

---

### Terrain interaction relationships  *(NEW in v3.0)*

| Relationship | From -> To | Properties | Description |
|---|---|---|---|
| `TERRAIN_INTERACTION` | `:Rule` -> `:Terrain` | `effect: String` | This special rule changes how a unit interacts with this terrain. |
| `TERRAIN_INTERACTION` | `:TroopType` -> `:Terrain` | `effect: String` | This troop type has a special interaction with terrain. |

**`effect` vocabulary:**

| Value | Meaning |
|---|---|
| `"ignores"` | Ignores all effects of this terrain (movement, disruption, cover) |
| `"ignores_cover"` | Ignores cover modifiers only |
| `"ignores_dangerous_test"` | Immune to the D6 Dangerous Terrain wound check |
| `"ignores_disruption"` | Does not become Disrupted even with 25%+ models in terrain |
| `"can_deploy_in"` | May be deployed inside this terrain during setup |
| `"move_through_freely"` | No movement penalty when passing through |
| `"cannot_enter"` | Cannot enter this terrain type at all |

---

### Semantic relationships (extracted from hyperlinks in rule text)

| Relationship | From -> To | Description |
|---|---|---|
| `REFERENCES` | `:Rule` -> `:Rule` | Rule mentions another rule |
| `REFERENCES` | `:Rule` -> `:CoreRule` | Rule references a core mechanic |
| `REFERENCES` | `:CoreRule` -> `:CoreRule` | Core mechanic references another |
| `REFERENCES` | `:CoreRule` -> `:Rule` | Core mechanic references a special rule |
| `REFERENCES` | `:Spell` -> `:Rule` | Spell references a special rule |
| `REFERENCES` | `:Spell` -> `:CoreRule` | Spell references a core mechanic |
| `REFERENCES` | `:MagicItem` -> `:Rule` | Magic item confers or references a rule |

---

### Clarification and correction relationships

| Relationship | From -> To | Description |
|---|---|---|
| `CLARIFIES` | `:FAQ` -> `:Rule` | FAQ clarifies a special rule |
| `CLARIFIES` | `:FAQ` -> `:CoreRule` | FAQ clarifies a core mechanic |
| `CLARIFIES` | `:FAQ` -> `:Unit` | FAQ clarifies a unit's profile or behaviour |
| `CLARIFIES` | `:FAQ` -> `:Spell` | FAQ clarifies a spell |
| `CLARIFIES` | `:FAQ` -> `:Weapon` | FAQ clarifies a weapon's profile or usage |
| `CLARIFIES` | `:FAQ` -> `:Terrain` | FAQ clarifies a terrain interaction (NEW v3.0) |
| `AMENDS` | `:Errata` -> `:Rule` | Errata corrects a special rule |
| `AMENDS` | `:Errata` -> `:CoreRule` | Errata corrects a core mechanic |
| `AMENDS` | `:Errata` -> `:Unit` | Errata modifies a unit's profile or equipment |
| `AMENDS` | `:Errata` -> `:Weapon` | Errata modifies a weapon's profile |
| `AMENDS` | `:Errata` -> `:Spell` | Errata modifies a spell |
| `AMENDS` | `:Errata` -> `:MagicItem` | Errata modifies a magic item |
| `AMENDS` | `:Errata` -> `:Terrain` | Errata modifies a terrain rule (NEW v3.0) |

---

## Relationship diagram

```
  :FAQ / :Errata ── CLARIFIES / AMENDS ──────────────────────────────────────┐
                                                                              │
  :Army ──BELONGS_TO◄── :Unit ──HAS_RULE──────────────────► :Rule ◄──────────┤
    │             │       │                                   │               │
    │  HAS_UNIT   │       │ HAS_WEAPON                        │ REFERENCES    │
    │             │       ▼                                   ▼               │
    │  ALLIED_WITH│     :Weapon (armour_value, shots,     :CoreRule ──────────┤
    ▼             │      template_type, bounce)                │              │
  :Army           │                               PART_OF_SECTION            │
                  │                                            │              │
   :TroopType ◄───┤ HAS_TYPE                             :CoreRule (parent)  │
        │         │   │                                                       │
        │  HAS_   │   │ HAS_UPGRADE                                           │
        │  INTRIN │   ▼                                  :Terrain ◄───────────┘
        │  SIC_   │ :Upgrade ─UNLOCKS_RULE──► :Rule ──TERRAIN_INTERACTION──► :Terrain
        │  RULE   │          ─UNLOCKS_ITEM──► :MagicItem
        ▼         │          ─UNLOCKS_WEAPON─► :Weapon  :TroopType ─TERRAIN_INTERACTION──► :Terrain
      :Rule        │
                  │ USES_LORE──► :Lore ◄──BELONGS_TO_LORE── :Spell
                  │
                  │ CAN_MOUNT──► :Unit (mounts)
                  │
                  └ SPLIT_PROFILE_OF──► :Unit (parent unit)
                  └ CAN_TAKE_ITEM──► :MagicItem
```

---

## Neo4j implementation notes

### Constraints and indexes (run once at startup)

```cypher
CREATE CONSTRAINT army_id        IF NOT EXISTS FOR (n:Army)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT unit_id        IF NOT EXISTS FOR (n:Unit)        REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT rule_id        IF NOT EXISTS FOR (n:Rule)        REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT corerule_id    IF NOT EXISTS FOR (n:CoreRule)    REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT trooptype_id   IF NOT EXISTS FOR (n:TroopType)   REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT terrain_id     IF NOT EXISTS FOR (n:Terrain)     REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT lore_id        IF NOT EXISTS FOR (n:Lore)        REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT spell_id       IF NOT EXISTS FOR (n:Spell)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT weapon_id      IF NOT EXISTS FOR (n:Weapon)      REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT magicitem_id   IF NOT EXISTS FOR (n:MagicItem)   REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT upgrade_id     IF NOT EXISTS FOR (n:Upgrade)     REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT faq_id         IF NOT EXISTS FOR (n:FAQ)         REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT errata_id      IF NOT EXISTS FOR (n:Errata)      REQUIRE n.id IS UNIQUE;

CREATE INDEX unit_url      IF NOT EXISTS FOR (n:Unit)    ON (n.url);
CREATE INDEX rule_url      IF NOT EXISTS FOR (n:Rule)    ON (n.url);
CREATE INDEX spell_url     IF NOT EXISTS FOR (n:Spell)   ON (n.url);
CREATE INDEX terrain_class IF NOT EXISTS FOR (n:Terrain) ON (n.terrain_class);
CREATE INDEX unit_army     IF NOT EXISTS FOR (n:Unit)    ON (n.troop_type_id);
```

### TroopType seed data

```python
# Source: tow.whfb.app/troop-types-at-a-glance/troop-type-table (Rulebook p.105)
TROOP_TYPE_SEED = [
    # Infantry
    {"id": "regular-infantry",  "category": "Infantry",    "min_models_for_rank_bonus": 5,    "max_rank_bonus": 2, "unit_strength_per_model": "1"},
    {"id": "heavy-infantry",    "category": "Infantry",    "min_models_for_rank_bonus": 4,    "max_rank_bonus": 2, "unit_strength_per_model": "1"},
    {"id": "monstrous-infantry","category": "Infantry",    "min_models_for_rank_bonus": 3,    "max_rank_bonus": 2, "unit_strength_per_model": "3"},
    {"id": "swarms",            "category": "Infantry",    "min_models_for_rank_bonus": None, "max_rank_bonus": None, "unit_strength_per_model": "3"},
    # Cavalry
    {"id": "light-cavalry",     "category": "Cavalry",     "min_models_for_rank_bonus": 5,    "max_rank_bonus": 1, "unit_strength_per_model": "2"},
    {"id": "heavy-cavalry",     "category": "Cavalry",     "min_models_for_rank_bonus": 4,    "max_rank_bonus": 1, "unit_strength_per_model": "2"},
    {"id": "monstrous-cavalry", "category": "Cavalry",     "min_models_for_rank_bonus": 3,    "max_rank_bonus": 1, "unit_strength_per_model": "3"},
    {"id": "war-beasts",        "category": "War Beasts",  "min_models_for_rank_bonus": 5,    "max_rank_bonus": 1, "unit_strength_per_model": "1"},
    # Chariots
    {"id": "light-chariots",    "category": "Chariots",    "min_models_for_rank_bonus": 3,    "max_rank_bonus": 1, "unit_strength_per_model": "3"},
    {"id": "heavy-chariots",    "category": "Chariots",    "min_models_for_rank_bonus": None, "max_rank_bonus": None, "unit_strength_per_model": "5"},
    # Monsters
    {"id": "monstrous-creatures","category": "Monsters",   "min_models_for_rank_bonus": None, "max_rank_bonus": None, "unit_strength_per_model": "As Starting Wounds"},
    {"id": "behemoths",         "category": "Monsters",    "min_models_for_rank_bonus": None, "max_rank_bonus": None, "unit_strength_per_model": "As Starting Wounds"},
    # War Machines
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

### Alliance edge seed (partial — expand from each army's composition page)

```python
ALLIANCE_SEED = [
    # Vampire Counts
    {"from": "vampire-counts",  "to": "tomb-kings-of-khemri",   "alliance_type": "trusted"},
    # Empire of Man
    {"from": "empire-of-man",   "to": "dwarfen-mountain-holds", "alliance_type": "trusted"},
    {"from": "empire-of-man",   "to": "grand-cathay",           "alliance_type": "trusted"},
    {"from": "empire-of-man",   "to": "kingdom-of-bretonnia",   "alliance_type": "trusted"},
    {"from": "empire-of-man",   "to": "wood-elf-realms",        "alliance_type": "suspicious"},
    # ... (complete list scraped from each army's Grand Army composition page)
]

def seed_alliances(driver, alliance_seed):
    with driver.session() as session:
        for entry in alliance_seed:
            session.run(
                """
                MATCH (a:Army {id: $from_id}), (b:Army {id: $to_id})
                MERGE (a)-[e:ALLIED_WITH]->(b)
                SET e.alliance_type = $alliance_type
                """,
                from_id=entry["from"], to_id=entry["to"],
                alliance_type=entry["alliance_type"],
            )
```

### Terrain interaction seed (partial — expand from special rule text parsing)

```python
TERRAIN_INTERACTION_SEED = [
    # Fly (X): ignores most terrain during movement
    {"from_label": "Rule", "from_id": "fly",               "to_id": "difficult-terrain",  "effect": "ignores"},
    {"from_label": "Rule", "from_id": "fly",               "to_id": "dangerous-terrain",  "effect": "ignores_dangerous_test"},
    {"from_label": "Rule", "from_id": "fly",               "to_id": "woods",              "effect": "ignores"},
    # Ethereal: ignores all terrain
    {"from_label": "Rule", "from_id": "ethereal",          "to_id": "difficult-terrain",  "effect": "ignores"},
    {"from_label": "Rule", "from_id": "ethereal",          "to_id": "dangerous-terrain",  "effect": "ignores"},
    {"from_label": "Rule", "from_id": "ethereal",          "to_id": "impassable-terrain", "effect": "ignores"},
    # Move Through Cover: ignores cover from woods
    {"from_label": "Rule", "from_id": "move-through-cover","to_id": "woods",              "effect": "ignores_cover"},
    # Scouts: can deploy in woods
    {"from_label": "Rule", "from_id": "scouts",            "to_id": "woods",              "effect": "can_deploy_in"},
    # Skirmishers: treat woods as open (no disruption)
    {"from_label": "Rule", "from_id": "skirmishers",       "to_id": "woods",              "effect": "ignores_disruption"},
    # ... (complete list derived from rule text parsing + manual curation)
]

def seed_terrain_interactions(driver, seed):
    with driver.session() as session:
        for entry in seed:
            query = f"""
                MATCH (source:{entry['from_label']} {{id: $from_id}}), (t:Terrain {{id: $to_id}})
                MERGE (source)-[e:TERRAIN_INTERACTION]->(t)
                SET e.effect = $effect
            """
            session.run(query, from_id=entry["from_id"],
                        to_id=entry["to_id"], effect=entry["effect"])
```

### Key query examples

```cypher
// Objective 2.2: Which armies can Vampire Counts ally with?
MATCH (vc:Army {id: "vampire-counts"})-[e:ALLIED_WITH]->(ally:Army)
RETURN ally.name AS ally_army, e.alliance_type AS alliance_type
ORDER BY e.alliance_type

// Objective 2.3: What are the rank-bonus rules and unit strength for Heavy Cavalry?
// (These are static troop-type properties — no army-list values involved.)
MATCH (t:TroopType {id: "heavy-cavalry"})
RETURN t.min_models_for_rank_bonus AS min_models_needed_per_rank_for_bonus,
       t.max_rank_bonus            AS max_rank_bonus_claimable,
       t.unit_strength_per_model   AS unit_strength_per_model

// Objective 2.4: Can Blood Knights charge through woods (any immunity)?
MATCH (u:Unit {id: "blood-knights"})-[:HAS_RULE]->(r:Rule)-[e:TERRAIN_INTERACTION]->(t:Terrain {id: "woods"})
RETURN r.name AS rule, e.effect AS effect
UNION
MATCH (u:Unit {id: "blood-knights"})-[:HAS_TYPE]->(tt:TroopType)-[e:TERRAIN_INTERACTION]->(t:Terrain {id: "woods"})
RETURN tt.name AS rule, e.effect AS effect

// Objective 1: Which rules let a unit ignore dangerous terrain tests?
MATCH (r:Rule)-[e:TERRAIN_INTERACTION]->(t:Terrain {id: "dangerous-terrain"})
WHERE e.effect IN ["ignores", "ignores_dangerous_test"]
RETURN r.name, r.url

// Objective 2.7: Points budget for Blood Knights standard bearer
MATCH (u:Unit {id: "blood-knights"})-[:HAS_UPGRADE]->(up:Upgrade {upgrade_type: "command_standard"})
RETURN up.description, up.points_cost, up.cost_unit, up.magic_standard_budget
```

### Creating nodes (Python neo4j-driver)

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

def create_unit(tx, data: dict):
    tx.run("""
        MERGE (u:Unit {id: $id})
        SET u += {
            url: $url, source_citation: $source_citation, last_updated: $last_updated,
            cost_points_per_model: $cost_points_per_model, unit_category: $unit_category,
            troop_type_id: $troop_type_id, army_category: $army_category,
            base_size_mm: $base_size_mm, unit_size: $unit_size,
            is_named_character: $is_named_character, wizard_level: $wizard_level,
            av_intrinsic: $av_intrinsic, profiles: $profiles,
            name: $name, i18n: $i18n
        }
    """, **data)

# Example call
with driver.session() as session:
    session.execute_write(create_unit, {
        "id": "blood-knights",
        "url": "https://tow.whfb.app/unit/blood-knights",
        "source_citation": {"book": "Vampire Counts", "page": 13},
        "last_updated": "2024-03-01",
        "cost_points_per_model": 39,
        "unit_category": "Cavalry",
        "troop_type_id": "heavy-cavalry",
        "army_category": "Rare",
        "base_size_mm": {"width": 30, "depth": 60},
        "unit_size": {"min": 5, "max": None},
        "is_named_character": False,
        "wizard_level": None,
        "av_intrinsic": None,  # AV comes from heavy armour + shield + barding equipment
        "profiles": [
            {"name": "Blood Knight", "M": None, "WS": 5, "BS": 3, "S": 4, "T": 4, "W": 1, "I": 4, "A": 2, "Ld": 7},
            {"name": "Kastellan",    "M": None, "WS": 5, "BS": 3, "S": 4, "T": 4, "W": 1, "I": 4, "A": 3, "Ld": 7},
            {"name": "Nightmare",    "M": 7,    "WS": 3, "BS": None, "S": 4, "T": None, "W": None, "I": 2, "A": 1, "Ld": None},
        ],
        "name": "Blood Knights",
        "i18n": {"en": {"name": "Blood Knights"}, "es": {"name": "Caballeros de Sangre"}},
    })
```

### Embedding generation

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")

def text_for_embedding(node_data: dict, lang: str = "en") -> str:
    """Return the text to embed for a node, with language fallback to English."""
    i18n = node_data.get("i18n", {})
    lang_data = i18n.get(lang, {})
    fields = ["text", "question", "answer", "name"]
    parts = []
    for f in fields:
        value = lang_data.get(f) or node_data.get(f)
        if value:
            parts.append(value)
    return " ".join(parts)

node = {"id": "fear", "name": "Fear", "text": "Units with Fear cause Fear in enemies..."}
embedding = model.encode(text_for_embedding(node, lang="en"))
# Store in ChromaDB/FAISS with metadata: {"id": node["id"], "url": node["url"]}
```

---

*End of schema v3.0*