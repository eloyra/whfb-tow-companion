"""
System-wide constants. These never change at runtime.
"""

# Mapping from stat abbreviation to CoreRule node id and URL.
# Used to resolve profile keys to graph nodes without adding
# redundant edges from every Unit to every characteristic node.
CHARACTERISTIC_MAP: dict[str, dict[str, str]] = {
    "M": {"id": "movement", "url": "https://tow.whfb.app/model-profiles/movement"},
    "WS": {"id": "weapon-skill", "url": "https://tow.whfb.app/model-profiles/weapon-skill"},
    "BS": {"id": "ballistic-skill", "url": "https://tow.whfb.app/model-profiles/ballistic-skill"},
    "S": {"id": "strength", "url": "https://tow.whfb.app/model-profiles/strength"},
    "T": {"id": "toughness", "url": "https://tow.whfb.app/model-profiles/toughness"},
    "W": {"id": "wounds", "url": "https://tow.whfb.app/model-profiles/wounds"},
    "I": {"id": "initiative", "url": "https://tow.whfb.app/model-profiles/initiative"},
    "A": {"id": "attacks", "url": "https://tow.whfb.app/model-profiles/attacks"},
    "Ld": {"id": "leadership", "url": "https://tow.whfb.app/model-profiles/leadership"},
}

# Languages with full support (scraping + translation)
SUPPORTED_LANGUAGES: list[str] = ["en", "es"]
DEFAULT_LANGUAGE: str = "en"

# Wiki base URL
WIKI_BASE_URL: str = "https://tow.whfb.app"

# ---------------------------------------------------------------------------
# TroopType rank-bonus and unit-strength seed data.
# Source: tow.whfb.app/troop-types-at-a-glance/troop-type-table (Rulebook p.105).
# Keys match the slugs used by /troop-types-in-detail/ pages AND by the
# troopType linked entries on unit pages.
# ---------------------------------------------------------------------------

TROOP_TYPE_SEED: dict[str, dict] = {
    # Infantry
    "regular-infantry": {
        "min_models_for_rank_bonus": 5,
        "max_rank_bonus": 2,
        "unit_strength_per_model": "1",
    },
    "heavy-infantry": {
        "min_models_for_rank_bonus": 4,
        "max_rank_bonus": 2,
        "unit_strength_per_model": "1",
    },
    "monstrous-infantry": {
        "min_models_for_rank_bonus": 3,
        "max_rank_bonus": 2,
        "unit_strength_per_model": "3",
    },
    "swarms": {
        "min_models_for_rank_bonus": None,
        "max_rank_bonus": None,
        "unit_strength_per_model": "3",
    },
    # Cavalry
    "light-cavalry": {
        "min_models_for_rank_bonus": 5,
        "max_rank_bonus": 1,
        "unit_strength_per_model": "2",
    },
    "heavy-cavalry": {
        "min_models_for_rank_bonus": 4,
        "max_rank_bonus": 1,
        "unit_strength_per_model": "2",
    },
    "monstrous-cavalry": {
        "min_models_for_rank_bonus": 3,
        "max_rank_bonus": 1,
        "unit_strength_per_model": "3",
    },
    "war-beasts": {
        "min_models_for_rank_bonus": 5,
        "max_rank_bonus": 1,
        "unit_strength_per_model": "1",
    },
    # Chariots
    "light-chariots": {
        "min_models_for_rank_bonus": 3,
        "max_rank_bonus": 1,
        "unit_strength_per_model": "3",
    },
    "heavy-chariots": {
        "min_models_for_rank_bonus": None,
        "max_rank_bonus": None,
        "unit_strength_per_model": "5",
    },
    # Monsters
    "monstrous-creatures": {
        "min_models_for_rank_bonus": None,
        "max_rank_bonus": None,
        "unit_strength_per_model": "As Starting Wounds",
    },
    "behemoths": {
        "min_models_for_rank_bonus": None,
        "max_rank_bonus": None,
        "unit_strength_per_model": "As Starting Wounds",
    },
    # War Machines
    "war-machines": {
        "min_models_for_rank_bonus": None,
        "max_rank_bonus": None,
        "unit_strength_per_model": "As Starting Wounds",
    },
}

# ---------------------------------------------------------------------------
# TroopType slug normalisation: armyListEntry.troopType uses singular CMS slugs;
# /troop-types-in-detail/ pages (and therefore TroopType node IDs) use plural URL slugs.
# Map singular → plural so HAS_TYPE edges resolve correctly.
# "named-character" is a unit-category leak — map to None to suppress the edge.
# ---------------------------------------------------------------------------

TROOP_TYPE_SLUG_MAP: dict[str, str | None] = {
    "behemoth": "behemoths",
    "heavy-chariot": "heavy-chariots",
    "light-chariot": "light-chariots",
    "monstrous-creature": "monstrous-creatures",
    "swarm": "swarms",
    "war-beast": "war-beasts",
    "war-machine": "war-machines",
    "named-character": None,  # unit category, not a troop type
}

# ---------------------------------------------------------------------------
# Magic item type normalisation: Contentful PascalCase → schema snake_case.
# ---------------------------------------------------------------------------

MAGIC_ITEM_TYPE_MAP: dict[str, str] = {
    "Magic Weapon": "magic_weapon",
    "Magic Armour": "magic_armour",
    "Talisman": "talisman",
    "Magic Standard": "magic_standard",
    "Enchanted Item": "enchanted_item",
    "Arcane Item": "arcane_item",
    "Ability": "ability",
    "Unique": "unique",
}

# ---------------------------------------------------------------------------
# Node types
# ---------------------------------------------------------------------------


class NodeType:
    ARMY = "army"
    UNIT = "unit"
    PROFILE = "profile"
    LORE = "lore"
    SPECIAL_RULE = "special_rule"
    CORE_RULE = "core_rule"
    DOCUMENT = "document"
    TROOP_TYPE = "troop_type"
    WEAPON = "weapon"
    SPELL = "spell"
    MAGIC_ITEM = "magic_item"
    FAQ = "faq"
    ERRATA = "errata"
    UPGRADE = "upgrade"
    COMPOSITION_LIST = "composition_list"
    COMPOSITION_SLOT = "composition_slot"


# ---------------------------------------------------------------------------
# Edge types
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Document classification: controls which wiki pages the CoreRule parser
# emits as :Document nodes instead of :CoreRule nodes.
#
# DOCUMENT_SECTIONS  — all pages under these URL section prefixes default to :Document.
# DOCUMENT_PAGES     — specific "section/slug" paths forced to :Document.
# CORE_RULE_PAGES    — specific "section/slug" paths promoted back to :CoreRule
#                      (overrides DOCUMENT_SECTIONS when a section is ambiguous).
# ---------------------------------------------------------------------------

DOCUMENT_SECTIONS: frozenset[str] = frozenset(
    {
        "overview-of-the-game",  # 6 pages: pure game-setup walkthrough; avg 0.7 links, max 2
        # All other sections are mixed — specific Document pages listed in DOCUMENT_PAGES below.
    }
)

DOCUMENT_PAGES: frozenset[str] = frozenset(
    {
        # general-principles: etiquette / convention pages
        "general-principles/take-backs-and-changing-ones-mind",
        "general-principles/the-most-important-rule",
        "general-principles/unusual-situations",
        # warhammer-battles: 9 logistics/orientation pages; 18 mechanics pages default to CoreRule
        "warhammer-battles/size-of-battlefield",
        "warhammer-battles/first-turn",
        "warhammer-battles/game-length-warhammer-battles",
        "warhammer-battles/conceding",
        "warhammer-battles/time-limit",
        "warhammer-battles/pitched-battles",
        "warhammer-battles/historical-recreation",
        "warhammer-battles/setting-up-your-battlefield",
        "warhammer-battles/choosing-a-pitched-battle-scenario",
        # narrative-battles: 14 orientation/flavor pages; 22 scenario/mechanics pages → CoreRule
        "narrative-battles/what-is-a-narrative-battle",
        "narrative-battles/historical-recreations",
        "narrative-battles/narrative-scenarios",
        "narrative-battles/open-play",
        "narrative-battles/armies-of-imagination",
        "narrative-battles/think-of-them-more-as-guidelines",
        "narrative-battles/the-games-master",
        "narrative-battles/the-role-of-a-gm",
        "narrative-battles/forging-a-narrative",
        "narrative-battles/narrative-locations",
        "narrative-battles/narrative-motives",
        "narrative-battles/linked-battles",
        "narrative-battles/campaign-narrative",
        "narrative-battles/the-dark-monolith",
        # matched-play: 5 event-logistics pages; 66 mechanics/scenario pages default to CoreRule
        "matched-play/organising-an-event",
        "matched-play/roles-and-responsibilties",
        "matched-play/the-pairing-of-players",
        "matched-play/an-alliance-of-warlords",
        "matched-play/gather-your-allies",
        # campaign-battles: all 12 pages are mechanics (campaign rules) — nothing to list here
    }
)

CORE_RULE_PAGES: frozenset[str] = frozenset()  # promotion overrides; empty by default


# ---------------------------------------------------------------------------
# Edge types
# ---------------------------------------------------------------------------


class EdgeType:
    # Structural
    BELONGS_TO = "BELONGS_TO"
    HAS_TYPE = "HAS_TYPE"
    HAS_PROFILE = "HAS_PROFILE"
    HAS_RULE = "HAS_RULE"
    HAS_OPTIONAL_RULE = "HAS_OPTIONAL_RULE"
    HAS_WEAPON = "HAS_WEAPON"
    HAS_OPTIONAL_WEAPON = "HAS_OPTIONAL_WEAPON"
    CAN_MOUNT = "CAN_MOUNT"
    CAN_TAKE_ITEM = "CAN_TAKE_ITEM"
    USES_LORE = "USES_LORE"
    BELONGS_TO_LORE = "BELONGS_TO_LORE"
    PART_OF_SECTION = "PART_OF_SECTION"
    # Upgrade edges
    HAS_UPGRADE = "HAS_UPGRADE"
    UNLOCKS_RULE = "UNLOCKS_RULE"
    UNLOCKS_WEAPON = "UNLOCKS_WEAPON"
    UNLOCKS_ITEM = "UNLOCKS_ITEM"
    UNLOCKS_MOUNT = "UNLOCKS_MOUNT"
    REPLACES_WEAPON = "REPLACES_WEAPON"
    # Army composition edges
    HAS_LIST = "HAS_LIST"
    HAS_SLOT = "HAS_SLOT"
    SLOT_ALLOWS = "SLOT_ALLOWS"
    ALLIED_WITH = "ALLIED_WITH"
    # Semantic
    REFERENCES = "REFERENCES"
    # Clarification
    CLARIFIES = "CLARIFIES"
    AMENDS = "AMENDS"


# ---------------------------------------------------------------------------
# Graph label mapping and embedding configuration
# ---------------------------------------------------------------------------

NODE_TYPE_TO_LABEL: dict[str, str] = {
    NodeType.ARMY: "Army",
    NodeType.UNIT: "Unit",
    NodeType.PROFILE: "Profile",
    NodeType.LORE: "Lore",
    NodeType.SPECIAL_RULE: "SpecialRule",
    NodeType.CORE_RULE: "CoreRule",
    NodeType.DOCUMENT: "Document",
    NodeType.TROOP_TYPE: "TroopType",
    NodeType.WEAPON: "Weapon",
    NodeType.SPELL: "Spell",
    NodeType.MAGIC_ITEM: "MagicItem",
    NodeType.FAQ: "FAQ",
    NodeType.ERRATA: "Errata",
    NodeType.UPGRADE: "Upgrade",
    NodeType.COMPOSITION_LIST: "CompositionList",
    NodeType.COMPOSITION_SLOT: "CompositionSlot",
}

# Labels for which embeddings are generated.
# Profile excluded — embedded via parent Unit.
# CompositionList/CompositionSlot excluded — pure structural nodes, no prose to embed.
EMBEDDABLE_LABELS: tuple[str, ...] = (
    "SpecialRule",
    "CoreRule",
    "Document",
    "TroopType",
    "Spell",
    "MagicItem",
    "Lore",
    "FAQ",
    "Errata",
    "Weapon",
    "Unit",
    "Army",
)

EMBEDDING_DIM: int = 768
VECTOR_INDEX_SIMILARITY: str = "cosine"
