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
```