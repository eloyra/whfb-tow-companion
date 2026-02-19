# Esquema del Grafo de Conocimiento
## Sistema de Asistencia Conversacional — Warhammer: The Old World
**Versión:** 1.0  
**Fuente de datos:** tow.whfb.app  
**Última revisión:** 2025-02-19

---

## Índice
1. [Principios de diseño](#principios-de-diseño)
2. [Constantes del sistema](#constantes-del-sistema)
3. [Tipos de nodos](#tipos-de-nodos)
4. [Tipos de aristas](#tipos-de-aristas)
5. [Diagrama de relaciones](#diagrama-de-relaciones)
6. [Notas de implementación](#notas-de-implementación)

---

## Principios de diseño

- **Inglés como idioma canónico.** Toda la información estructural y los textos fuente se almacenan en inglés. Las traducciones se añaden en el campo `i18n` de cada nodo sin modificar la estructura del grafo.
- **`i18n` solo para campos traducibles.** Los campos invariantes (`id`, `url`, `source_citation`, stats numéricos, fechas) nunca se duplican en `i18n`.
- **Embeddings multilingües.** El sistema usa un modelo de embeddings multilingüe (ej. `paraphrase-multilingual-mpnet-base-v2`) que permite queries en cualquier idioma sin necesidad de traducir la query.
- **Relaciones de características como constantes.** La correspondencia entre abreviaturas de perfil (`WS`, `BS`...) y sus nodos `CoreRule` se resuelve mediante una tabla de constantes (`CHARACTERISTIC_MAP`), no mediante aristas del grafo, para evitar ruido estructural.
- **Redundancia controlada.** Los campos `troop_type_id` y `unit_category_id` se almacenan como atributos del nodo `Unit` además de existir como aristas `HAS_TYPE`, para facilitar la serialización al vector store sin traversal de grafo.

---

## Constantes del sistema

```python
# Mapa de abreviaturas de perfil a nodos CoreRule
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

# Idiomas soportados
SUPPORTED_LANGUAGES = ["en", "es"]
DEFAULT_LANGUAGE = "en"
```

---

## Tipos de nodos

### `Army`
Representa cada facción jugable. Nodo raíz del que cuelgan todas las unidades.

```python
{
    # --- Invariantes ---
    "id":               str,    # slug único. Ej: "vampire-counts"
    "url":              str,    # "https://tow.whfb.app/army/vampire-counts"
    "source_citation": {
        "book":         str,    # "Vampire Counts"
        "page":         int | None
    },
    "last_updated":     str,    # ISO 8601: "2024-03-01"

    # --- Canónico inglés ---
    "name":             str,    # "Vampire Counts"

    # --- Traducciones ---
    "i18n": {
        "en": {"name": str},
        "es": {"name": str},
        # extensible: "fr", "de", ...
    }
}
```

---

### `Unit`
Representa unidades, personajes y monturas con perfil estadístico.

```python
{
    # --- Invariantes ---
    "id":               str,    # slug único. Ej: "blood-knights"
    "url":              str,    # "https://tow.whfb.app/unit/blood-knights"
    "source_citation": {
        "book":         str,    # "Vampire Counts"
        "page":         int | None
    },
    "last_updated":     str,    # ISO 8601: "2024-03-01"

    "cost_points_per_model": int,   # 39 (siempre unitario; personajes únicos tienen unit_size.max=1)

    "unit_category_id": str,    # slug del nodo TroopType. Ej: "cavalry"
    "troop_type_id":    str,    # slug del nodo TroopType. Ej: "heavy-cavalry"

    "base_size_mm": {
        "width":        int,    # dimensión frontal en mm. Ej: 30
        "depth":        int     # dimensión de profundidad en mm. Ej: 60
    },

    "unit_size": {
        "min":          int,    # mínimo de modelos. Ej: 5
        "max":          int | None  # None = sin límite explícito; 1 para personajes/monstruos únicos
    },

    # Lista de subperfiles (puede ser 1 o varios si la unidad tiene rider+mount, champion, etc.)
    # Las claves de stats son las abreviaturas canónicas del juego.
    # None representa "-" en la wiki (característica no aplicable a ese subfil).
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

    # --- Canónico inglés ---
    "name":             str,    # "Blood Knights"

    # --- Traducciones ---
    "i18n": {
        "en": {"name": str},
        "es": {"name": str},
    }
}
```

> **Nota sobre `profiles`:** El nombre de cada subperfil (`"name"`) es invariante (nombre propio del juego). Los valores numéricos son invariantes. No hay campo `text` en `Unit` porque el contenido textual de una unidad se distribuye entre los nodos `Rule`, `Weapon` y `MagicItem` enlazados por aristas.

---

### `Rule`
Representa reglas especiales: universales, de ejército o únicas de unidad.

```python
{
    # --- Invariantes ---
    "id":               str,    # slug. Ej: "necromantic-undead", "fear"
    "url":              str,    # "https://tow.whfb.app/special-rules/fear"
    "source_citation": {
        "book":         str,    # "Rulebook" o "Vampire Counts"
        "page":         int | None
    },
    "last_updated":     str,    # ISO 8601

    # Ámbito de la regla:
    # "universal" → válida para todos los ejércitos
    # "army"      → específica de un ejército (army_id obligatorio)
    # "unique"    → específica de una unidad concreta
    "rule_scope":       str,    # "universal" | "army" | "unique"
    "army_id":          str | None,  # slug del ejército si rule_scope = "army"

    # --- Canónico inglés ---
    "name":             str,    # "Fear"
    "text":             str,    # texto completo de la regla en inglés

    # --- Traducciones ---
    "i18n": {
        "en": {"name": str, "text": str},
        "es": {"name": str, "text": str},
    }
}
```

---

### `CoreRule`
Representa páginas de mecánicas generales del reglamento (fases de juego, movimiento, disparo, magia, perfiles, terreno, etc.). Se diferencia de `Rule` en que no es una regla especial que posee una unidad, sino una mecánica del sistema.

```python
{
    # --- Invariantes ---
    "id":               str,    # slug. Ej: "the-charge-move"
    "url":              str,    # "https://tow.whfb.app/movement-in-detail/the-charge-move"
    "source_citation": {
        "book":         str,    # "Rulebook"
        "page":         int | None
    },
    "last_updated":     str,    # ISO 8601

    "section":          str,    # sección padre en la wiki. Ej: "movement-in-detail"
    "section_id":       str,    # slug de la sección padre. Ej: "movement-in-detail"

    # Navegación secuencial (útil para contexto en retrieval)
    "prev_page_url":    str | None,
    "next_page_url":    str | None,

    # --- Canónico inglés ---
    "name":             str,    # "The Charge Move"
    "text":             str,    # texto completo

    # --- Traducciones ---
    "i18n": {
        "en": {"name": str, "text": str},
        "es": {"name": str, "text": str},
    }
}
```

---

### `TroopType`
Representa los tipos y subtipos de tropa del reglamento. Los nodos existen en la wiki bajo `/troop-types-in-detail/`.

```python
{
    # --- Invariantes ---
    "id":               str,    # slug. Ej: "heavy-cavalry"
    "url":              str,    # "https://tow.whfb.app/troop-types-in-detail/heavy-cavalry"
    "source_citation": {
        "book":         str,
        "page":         int | None
    },
    "last_updated":     str,

    "category":         str,    # categoría de nivel superior. Ej: "cavalry", "infantry", "monster"

    # --- Canónico inglés ---
    "name":             str,    # "Heavy Cavalry"
    "text":             str,    # descripción del tipo de tropa

    # --- Traducciones ---
    "i18n": {
        "en": {"name": str, "text": str},
        "es": {"name": str, "text": str},
    }
}
```

---

### `Weapon`
Representa armas, armaduras y equipo adicional.

```python
{
    # --- Invariantes ---
    "id":               str,    # slug. Ej: "lance"
    "url":              str,    # "https://tow.whfb.app/weapons-of-war/lance"
    "source_citation": {
        "book":         str,
        "page":         int | None
    },
    "last_updated":     str,

    # Clasificación del equipo
    "weapon_class":     str,    # "melee" | "missile" | "armour" | "equipment"

    # --- Canónico inglés ---
    "name":             str,    # "Lance"
    "text":             str,    # descripción completa con reglas de uso

    # --- Traducciones ---
    "i18n": {
        "en": {"name": str, "text": str},
        "es": {"name": str, "text": str},
    }
}
```

---

### `Spell`
Representa hechizos individuales de los Lores de Magia.

```python
{
    # --- Invariantes ---
    "id":               str,    # slug. Ej: "invocation-of-nehek"
    "url":              str,    # URL de la página del lore (con anchor al hechizo si aplica)
    "source_citation": {
        "book":         str,
        "page":         int | None
    },
    "last_updated":     str,

    "lore_id":          str,    # slug del lore. Ej: "necromancy"
    "casting_value":    int,    # valor de lanzamiento
    "spell_type":       str,    # "Hex" | "Magic Missile" | "Conveyance" | "Enchantment" |
                                # "Assailment" | "Magical Vortex" | "Bound Spell"

    # --- Canónico inglés ---
    "name":             str,    # "Invocation of Nehek"
    "text":             str,    # texto completo del hechizo

    # --- Traducciones ---
    "i18n": {
        "en": {"name": str, "text": str},
        "es": {"name": str, "text": str},
    }
}
```

---

### `MagicItem`
Representa ítems mágicos universales y poderes específicos de ejército (ej. Vampiric Powers).

```python
{
    # --- Invariantes ---
    "id":               str,    # slug. Ej: "sword-of-battle"
    "url":              str,    # "https://tow.whfb.app/magic-items/magic-weapons"
    "source_citation": {
        "book":         str,
        "page":         int | None
    },
    "last_updated":     str,

    "item_type":        str,    # "magic_weapon" | "magic_armour" | "talisman" |
                                # "magic_standard" | "enchanted_item" | "arcane_item" |
                                # "vampiric_power" | (otros poderes de ejército)
    "points_cost":      int | None,  # coste en puntos; None si es variable
    "army_id":          str | None,  # None si es universal; slug del ejército si es exclusivo

    # --- Canónico inglés ---
    "name":             str,
    "text":             str,    # descripción completa incluyendo efectos de juego

    # --- Traducciones ---
    "i18n": {
        "en": {"name": str, "text": str},
        "es": {"name": str, "text": str},
    }
}
```

---

### `FAQ`
Representa preguntas frecuentes oficiales integradas en la wiki.

```python
{
    # --- Invariantes ---
    "id":               str,    # slug generado. Ej: "faq-regeneration-flaming-attacks"
    "url":              str,    # "https://tow.whfb.app/faq" (con anchor si aplica)
    "source_citation": {
        "book":         str,    # "FAQ 2024"
        "page":         int | None
    },
    "last_updated":     str,

    # --- Canónico inglés ---
    "question":         str,    # texto de la pregunta
    "answer":           str,    # texto de la respuesta

    # --- Traducciones ---
    "i18n": {
        "en": {"question": str, "answer": str},
        "es": {"question": str, "answer": str},
    }
}
```

---

### `Errata`
Representa correcciones y enmiendas oficiales integradas en la wiki.

```python
{
    # --- Invariantes ---
    "id":               str,    # slug generado. Ej: "errata-regeneration-2024-01"
    "url":              str,    # "https://tow.whfb.app/errata"
    "source_citation": {
        "book":         str,    # "Errata & Amendments 2024"
        "page":         int | None
    },
    "last_updated":     str,

    # --- Canónico inglés ---
    "original_text":    str,    # texto original corregido
    "corrected_text":   str,    # texto correcto tras la enmienda

    # --- Traducciones ---
    "i18n": {
        "en": {"original_text": str, "corrected_text": str},
        "es": {"original_text": str, "corrected_text": str},
    }
}
```

---

## Tipos de aristas

Las aristas son **dirigidas**. El grafo se implementa como `networkx.DiGraph`.

### Relaciones estructurales

| Arista | De → A | Descripción | Ejemplo |
|---|---|---|---|
| `BELONGS_TO` | `Unit` → `Army` | Unidad pertenece a un ejército | Blood Knights → Vampire Counts |
| `HAS_TYPE` | `Unit` → `TroopType` | Tipo de tropa de la unidad | Blood Knights → Heavy Cavalry |
| `HAS_RULE` | `Unit` → `Rule` | Regla especial base de la unidad (siempre activa) | Blood Knights → Regeneration |
| `HAS_OPTIONAL_RULE` | `Unit` → `Rule` | Regla adquirible como upgrade de puntos | Blood Knights → Drilled |
| `HAS_WEAPON` | `Unit` → `Weapon` | Equipo estándar incluido en el coste base | Blood Knights → Lance |
| `HAS_OPTIONAL_WEAPON` | `Unit` → `Weapon` | Equipo opcional o reemplazable | Vampire Count → Great Weapon |
| `CAN_MOUNT` | `Unit` → `Unit` | Personaje puede montar esta montura | Vampire Count → Zombie Dragon |
| `CAN_TAKE_ITEM` | `Unit` → `MagicItem` | Puede comprar ítems de esta categoría | Vampire Count → Vampiric Powers |
| `USES_LORE` | `Unit` → `Spell` | Mago puede usar hechizos de este lore | Vampire Count → Necromancy |
| `PART_OF_SECTION` | `CoreRule` → `CoreRule` | Relación jerárquica padre-hijo de sección | The Charge Move → Movement in Detail |

### Atributos de aristas con coste

Las aristas que representan upgrades de puntos llevan un atributo `cost`:

```python
# Ejemplo: Blood Knights pueden adquirir Drilled por +3 pts/modelo
graph.add_edge("blood-knights", "drilled",
    relation="HAS_OPTIONAL_RULE",
    cost=3,
    cost_unit="per_model"   # "per_model" | "per_unit" | "fixed"
)
```

### Relaciones semánticas (extraídas de hiperlinks en el texto)

| Arista | De → A | Descripción | Fuente de extracción |
|---|---|---|---|
| `REFERENCES` | `Rule` → `Rule` | Regla menciona o cita otra regla | Links en el cuerpo de texto |
| `REFERENCES` | `Rule` → `CoreRule` | Regla cita una mecánica del reglamento | Links en el cuerpo de texto |
| `REFERENCES` | `CoreRule` → `CoreRule` | Mecánica cita otra mecánica | Links en el cuerpo de texto |
| `REFERENCES` | `CoreRule` → `Rule` | Mecánica cita una regla especial | Links en el cuerpo de texto |
| `REFERENCES` | `Spell` → `Rule` | Hechizo cita una regla especial | Links en el cuerpo de texto |
| `REFERENCES` | `Spell` → `CoreRule` | Hechizo cita una mecánica | Links en el cuerpo de texto |

### Relaciones de clarificación y corrección

| Arista | De → A | Descripción |
|---|---|---|
| `CLARIFIES` | `FAQ` → `Rule` | FAQ aclara una regla especial |
| `CLARIFIES` | `FAQ` → `CoreRule` | FAQ aclara una mecánica del reglamento |
| `CLARIFIES` | `FAQ` → `Unit` | FAQ aclara el perfil o comportamiento de una unidad |
| `AMENDS` | `Errata` → `Rule` | Errata corrige el texto de una regla especial |
| `AMENDS` | `Errata` → `CoreRule` | Errata corrige una mecánica del reglamento |
| `AMENDS` | `Errata` → `Unit` | Errata modifica el perfil o equipo de una unidad |

---

## Diagrama de relaciones

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

## Notas de implementación

### Serialización del grafo

NetworkX serializa el grafo a GraphML o JSON. Los atributos deben ser tipos primitivos o strings JSON para compatibilidad:

```python
import networkx as nx
import json

G = nx.DiGraph()

# Los atributos compuestos (dicts, lists) se serializan como JSON strings
node_data = {
    "id": "blood-knights",
    "source_citation": json.dumps({"book": "Vampire Counts", "page": 13}),
    "profiles": json.dumps([{"name": "Blood Knight", "WS": 5, ...}]),
    "base_size_mm": json.dumps({"width": 30, "depth": 60}),
    "i18n": json.dumps({"en": {"name": "Blood Knights"}, "es": {"name": "Caballeros de Sangre"}}),
    # Primitivos directamente:
    "cost_points_per_model": 39,
    "last_updated": "2024-03-01",
    "name": "Blood Knights",
}
G.add_node("blood-knights", **node_data)
```

### Generación de embeddings

Se genera un embedding por nodo y por idioma soportado, usando el campo `text` (o `question`+`answer` para FAQ):

```python
# Para modelos multilingües, los textos en distintos idiomas
# se proyectan al mismo espacio vectorial:
# → una query en español encuentra nodos con texto en inglés

from sentence_transformers import SentenceTransformer
model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")

for node_id, data in G.nodes(data=True):
    text_en = data.get("text", data.get("name", ""))
    embedding = model.encode(text_en)
    # Almacenar en vector store (ChromaDB / FAISS) con metadata del nodo
```

### Añadir un idioma nuevo

El proceso no modifica la estructura del grafo:

```python
def add_language(G, lang_code, translation_fn):
    """Añade traducciones a todos los nodos sin modificar la estructura del grafo."""
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

### Fallback de idioma

En tiempo de query, si el idioma solicitado no está disponible se usa inglés:

```python
def get_text(node_data, lang, field="text"):
    i18n = json.loads(node_data.get("i18n", "{}"))
    if lang in i18n and field in i18n[lang]:
        return i18n[lang][field]
    return node_data.get(field, "")  # fallback a inglés canónico
```