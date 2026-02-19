"""
System-wide constants. These never change at runtime.
"""

# Mapping from stat abbreviation to CoreRule node id and URL.
# Used to resolve profile keys to graph nodes without adding
# redundant edges from every Unit to every characteristic node.
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

# Languages with full support (scraping + translation)
SUPPORTED_LANGUAGES: list[str] = ["en", "es"]
DEFAULT_LANGUAGE: str = "en"

# Wiki base URL
WIKI_BASE_URL: str = "https://tow.whfb.app"

# Node types (used as NetworkX node attribute "node_type")
class NodeType:
    ARMY        = "army"
    UNIT        = "unit"
    RULE        = "rule"
    CORE_RULE   = "core_rule"
    TROOP_TYPE  = "troop_type"
    WEAPON      = "weapon"
    SPELL       = "spell"
    MAGIC_ITEM  = "magic_item"
    FAQ         = "faq"
    ERRATA      = "errata"

# Edge types (used as NetworkX edge attribute "relation")
class EdgeType:
    # Structural
    BELONGS_TO          = "BELONGS_TO"
    HAS_TYPE            = "HAS_TYPE"
    HAS_RULE            = "HAS_RULE"
    HAS_OPTIONAL_RULE   = "HAS_OPTIONAL_RULE"
    HAS_WEAPON          = "HAS_WEAPON"
    HAS_OPTIONAL_WEAPON = "HAS_OPTIONAL_WEAPON"
    CAN_MOUNT           = "CAN_MOUNT"
    CAN_TAKE_ITEM       = "CAN_TAKE_ITEM"
    USES_LORE           = "USES_LORE"
    PART_OF_SECTION     = "PART_OF_SECTION"
    # Semantic
    REFERENCES          = "REFERENCES"
    # Clarification
    CLARIFIES           = "CLARIFIES"
    AMENDS              = "AMENDS"
