"""
Rich-text walker that converts a unit's ``options`` field into :Upgrade nodes.

Public API:
    parse_options_to_upgrades(unit_slug, options_rt, profile_slug_set, source_citation)
        -> (list[upgrade_dict], list[edge_dict])

Each upgrade_dict carries a ``node_type`` key so the coordinator can route it to
``upgrades.json``.  Each edge_dict carries ``src``, ``dst``, ``relation``,
``properties``.

Edge relation conventions:
    HAS_UPGRADE    — unit → upgrade
    UNLOCKS_MOUNT  — upgrade → armyListEntry mount
    UNLOCKS_RULE   — upgrade → rule/weapon/item (provisional; two-pass relabels)
    REPLACES_WEAPON — upgrade → weapon being replaced (first link in a swap)
"""

from __future__ import annotations

import re

from pipeline.constants import EdgeType, NodeType

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_COST_RE = re.compile(r"\(\s*\+(\d+)\s*point[s]?(?:\s+per\s+(model|unit))?\s*\)", re.IGNORECASE)
_BUDGET_RE = re.compile(
    r"up\s+to\s+(?:a\s+total\s+of\s+)?(\d+)\s+(?:points?|pts)", re.IGNORECASE
)
_MAGIC_STANDARD_BUDGET_RE = re.compile(
    r"(?:magic\s+standard|standard)\s+(?:worth\s+)?up\s+to", re.IGNORECASE
)
_WIZARD_RE = re.compile(r"be\s+a\s+level\s+(\d+)\s+wizard", re.IGNORECASE)
_CHAMPION_RE = re.compile(
    r"upgrade\s+one\s+model\s+to\s+(?:a\s+|an\s+)?"
    r"([\w\s\-]+?)(?:\s*\(champion\))?\s*\(\s*\+",
    re.IGNORECASE,
)
_STANDARD_RE = re.compile(r"upgrade\s+one\s+model\s+to\s+a\s+standard\s+bearer", re.IGNORECASE)
_MUSICIAN_RE = re.compile(
    r"upgrade\s+one\s+model\s+to\s+(?:a\s+)?[\w\s\-]*\(musician\)"
    r"|upgrade\s+one\s+model\s+to\s+a\s+musician",
    re.IGNORECASE,
)
_REPLACE_RE = re.compile(r"\breplace\b", re.IGNORECASE)
_CONSTRAINT_RE = re.compile(r"^0-(\d+)\s+unit", re.IGNORECASE)
_PROFILE_SCOPE_RE = re.compile(r"^An?\s+([\w\s\-]+?)\s+may\b", re.IGNORECASE)
_MOUNT_HEADER_RE = re.compile(r"may\s+be\s+mounted", re.IGNORECASE)
_MUTEX_HEADER_RE = re.compile(r"may\s+take\s+one\s+of\s+the\s+following", re.IGNORECASE)
_ARMOUR_RE = re.compile(
    r"\b(?:heavy\s+armour|light\s+armour|full\s+plate(?:\s+armour)?|barding|shield(?:\s+\w+)?|coat\s+of\s+plates?|dragon\s+armour|gromril\s+armour|ithilmar\s+armour|enchanted\s+shield)\b",
    re.IGNORECASE,
)

# Slugs whose presence in entry-hyperlinks identifies typed budget categories
_BUDGET_SLUG_TO_TYPE: dict[str, str] = {
    "vampiric-powers": "vampiric_powers_budget",
    "weapon-runes": "rune_budget",
    "armour-runes": "rune_budget",
    "standard-runes": "rune_budget",
    "talismanic-runes": "rune_budget",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_options_to_upgrades(
    unit_slug: str,
    options_rt: dict | None,
    profile_slug_set: set[str],
    source_citation: dict,
) -> tuple[list[dict], list[dict]]:
    """Parse *options_rt* Contentful rich-text into Upgrade nodes + edges.

    Returns ``(upgrade_dicts, edge_dicts)``.
    """
    if not options_rt:
        return [], []

    top_list = _first_unordered_list(options_rt)
    if top_list is None:
        return [], []

    upgrades: list[dict] = []
    edges: list[dict] = []
    order = 0
    mutex_counter = 0

    for top_item in _list_items(top_list):
        para_text = _paragraph_text(top_item)
        nested = _nested_unordered_list(top_item)

        if nested:
            # Group header — propagate context to children
            header = para_text.strip().rstrip(":").strip()

            is_mutex = bool(_MUTEX_HEADER_RE.search(header))
            is_mount_group = bool(_MOUNT_HEADER_RE.search(header))
            is_constraint = bool(_CONSTRAINT_RE.match(header))
            availability_constraint: str | None = header if is_constraint else None

            mutex_group: str | None = None
            if is_mutex:
                mutex_counter += 1
                mutex_group = f"{unit_slug}#mg{mutex_counter}"

            # Profile-scoped group ("A Royal Clan Veteran may purchase:")
            scope_profile = _match_profile_scope(header, unit_slug, profile_slug_set)

            for child_item in _list_items(nested):
                child_text = _paragraph_text(child_item)
                child_links = _entry_links(child_item)

                up, edgs = _classify_and_emit(
                    unit_slug=unit_slug,
                    order=order,
                    text=child_text,
                    links=child_links,
                    source_citation=source_citation,
                    mutex_group=mutex_group,
                    availability_constraint=availability_constraint,
                    force_mount=is_mount_group,
                    applies_to_profile=scope_profile,
                )
                upgrades.append(up)
                edges.extend(edgs)
                order += 1
        else:
            # Top-level leaf
            item_text = _paragraph_text(top_item)
            item_links = _entry_links(top_item)

            # Profile-scoped leaf ("A Seneschal may purchase...")
            scope_profile = _match_profile_scope(item_text, unit_slug, profile_slug_set)

            # Mount via armyListEntry at top level (wight-king "May be mounted on a X")
            force_mount = any(ct == "armyListEntry" for _, ct in item_links)

            up, edgs = _classify_and_emit(
                unit_slug=unit_slug,
                order=order,
                text=item_text,
                links=item_links,
                source_citation=source_citation,
                force_mount=force_mount,
                applies_to_profile=scope_profile,
            )
            upgrades.append(up)
            edges.extend(edgs)
            order += 1

    return upgrades, edges


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


def _classify_and_emit(
    unit_slug: str,
    order: int,
    text: str,
    links: list[tuple[str, str]],
    source_citation: dict,
    mutex_group: str | None = None,
    availability_constraint: str | None = None,
    force_mount: bool = False,
    applies_to_profile: str | None = None,
) -> tuple[dict, list[dict]]:
    """Return (upgrade_node_dict, edge_dicts) for one leaf option."""
    upgrade_id = f"{unit_slug}#upgrade-{order}"
    linked_slugs = [slug for slug, _ in links]

    # --- Standard bearer ---
    if _STANDARD_RE.search(text):
        pts, cu = _cost_and_unit(text)
        magic_standard_match = _BUDGET_RE.search(text)
        magic_standard_budget = int(magic_standard_match.group(1)) if (
            magic_standard_match and _MAGIC_STANDARD_BUDGET_RE.search(text)
        ) else None
        node = _make_upgrade_node(
            upgrade_id,
            unit_slug,
            text,
            "Standard Bearer",
            "command_standard",
            source_citation,
            points_cost=pts,
            cost_unit=cu or "per_unit",
            magic_standard_budget=magic_standard_budget,
            mutex_group=mutex_group,
            applies_to_profile=applies_to_profile,
            availability_constraint=availability_constraint,
            order=order,
        )
        edgs = _make_edges(unit_slug, upgrade_id, links, is_replace=False)
        return node, edgs

    # --- Musician ---
    if _MUSICIAN_RE.search(text):
        pts, cu = _cost_and_unit(text)
        node = _make_upgrade_node(
            upgrade_id,
            unit_slug,
            text,
            "Musician",
            "command_musician",
            source_citation,
            points_cost=pts,
            cost_unit=cu or "per_unit",
            mutex_group=mutex_group,
            applies_to_profile=applies_to_profile,
            availability_constraint=availability_constraint,
            order=order,
        )
        edgs = _make_edges(unit_slug, upgrade_id, links, is_replace=False)
        return node, edgs

    # --- Champion ---
    m_champ = _CHAMPION_RE.search(text)
    if m_champ:
        champ_name = m_champ.group(1).strip().title()
        pts, cu = _cost_and_unit(text)
        budget_match = _BUDGET_RE.search(text)
        points_budget = int(budget_match.group(1)) if budget_match else None
        node = _make_upgrade_node(
            upgrade_id,
            unit_slug,
            text,
            f"Champion ({champ_name})",
            "command_champion",
            source_citation,
            points_cost=pts,
            cost_unit=cu or "per_unit",
            points_budget=points_budget,
            mutex_group=mutex_group,
            applies_to_profile=applies_to_profile,
            availability_constraint=availability_constraint,
            order=order,
        )
        edgs = _make_edges(unit_slug, upgrade_id, links, is_replace=False)
        return node, edgs

    # --- Budget ---
    m_budget = _BUDGET_RE.search(text)
    if m_budget:
        budget = int(m_budget.group(1))
        upgrade_type = _budget_type(text, linked_slugs)
        name = _budget_name(text, upgrade_type, links)
        node = _make_upgrade_node(
            upgrade_id,
            unit_slug,
            text,
            name,
            upgrade_type,
            source_citation,
            points_budget=budget,
            cost_unit="budget",
            mutex_group=mutex_group,
            applies_to_profile=applies_to_profile,
            availability_constraint=availability_constraint,
            order=order,
        )
        edgs = _make_edges(unit_slug, upgrade_id, links, is_replace=False)
        return node, edgs

    # --- Wizard level ---
    m_wizard = _WIZARD_RE.search(text)
    if m_wizard:
        level = int(m_wizard.group(1))
        pts, cu = _cost_and_unit(text)
        node = _make_upgrade_node(
            upgrade_id,
            unit_slug,
            text,
            f"Level {level} Wizard",
            "wizard_level",
            source_citation,
            points_cost=pts,
            cost_unit=cu or "flat",
            mutex_group=mutex_group,
            applies_to_profile=applies_to_profile,
            availability_constraint=availability_constraint,
            order=order,
        )
        edgs = _make_edges(unit_slug, upgrade_id, links, is_replace=False)
        return node, edgs

    # --- Mount ---
    if force_mount or any(ct == "armyListEntry" for _, ct in links):
        pts, cu = _cost_and_unit(text)
        mount_name = _derive_mount_name(text, links)
        node = _make_upgrade_node(
            upgrade_id,
            unit_slug,
            text,
            mount_name,
            "mount",
            source_citation,
            points_cost=pts,
            cost_unit=cu or "flat",
            mutex_group=mutex_group,
            applies_to_profile=applies_to_profile,
            availability_constraint=availability_constraint,
            order=order,
        )
        edgs = _make_edges(unit_slug, upgrade_id, links, is_replace=False)
        return node, edgs

    # --- Equipment swap ---
    if _REPLACE_RE.search(text) and len(links) >= 1:
        pts, cu = _cost_and_unit(text)
        # First rule-link = item being replaced; rest = replacements
        rule_links = [(s, ct) for s, ct in links if ct != "armyListEntry"]
        replaces_id = rule_links[0][0] if len(rule_links) >= 2 else None
        node = _make_upgrade_node(
            upgrade_id,
            unit_slug,
            text,
            _derive_swap_name(text, links),
            "weapon_replace",
            source_citation,
            points_cost=pts,
            cost_unit=cu or "per_model",
            replaces_weapon_id=replaces_id,
            mutex_group=mutex_group,
            applies_to_profile=applies_to_profile,
            availability_constraint=availability_constraint,
            order=order,
        )
        edgs = _make_edges(unit_slug, upgrade_id, links, is_replace=True)
        return node, edgs

    # --- Armour / shield addition ---
    if _ARMOUR_RE.search(text) and not _REPLACE_RE.search(text):
        pts, cu = _cost_and_unit(text)
        name = _derive_generic_name(text, links)
        node = _make_upgrade_node(
            upgrade_id,
            unit_slug,
            text,
            name,
            "armour_add",
            source_citation,
            points_cost=pts,
            cost_unit=cu or "per_model",
            mutex_group=mutex_group,
            applies_to_profile=applies_to_profile,
            availability_constraint=availability_constraint,
            order=order,
        )
        edgs = _make_edges(unit_slug, upgrade_id, links, is_replace=False)
        return node, edgs

    # --- Catch-all: rule_add (also covers weapon/armour additions) ---
    pts, cu = _cost_and_unit(text)
    name = _derive_generic_name(text, links)
    node = _make_upgrade_node(
        upgrade_id,
        unit_slug,
        text,
        name,
        "rule_add",
        source_citation,
        points_cost=pts,
        cost_unit=cu,
        mutex_group=mutex_group,
        applies_to_profile=applies_to_profile,
        availability_constraint=availability_constraint,
        order=order,
    )
    edgs = _make_edges(unit_slug, upgrade_id, links, is_replace=False)
    return node, edgs


# ---------------------------------------------------------------------------
# Node factory
# ---------------------------------------------------------------------------


def _make_upgrade_node(
    upgrade_id: str,
    unit_slug: str,
    description: str,
    name: str,
    upgrade_type: str,
    source_citation: dict,
    *,
    points_cost: int | None = None,
    cost_unit: str | None = None,
    points_budget: int | None = None,
    magic_standard_budget: int | None = None,
    replaces_weapon_id: str | None = None,
    mutex_group: str | None = None,
    applies_to_profile: str | None = None,
    availability_constraint: str | None = None,
    order: int = 0,
) -> dict:
    return {
        "node_type": NodeType.UPGRADE,
        "id": upgrade_id,
        "url": f"https://tow.whfb.app/unit/{unit_slug}",
        "name": name,
        "description": description.strip(),
        "upgrade_type": upgrade_type,
        "points_cost": points_cost,
        "cost_unit": cost_unit,
        "points_budget": points_budget,
        "magic_standard_budget": magic_standard_budget,
        "mutex_group": mutex_group,
        "applies_to_profile": applies_to_profile,
        "availability_constraint": availability_constraint,
        "replaces_weapon_id": replaces_weapon_id,
        "order": order,
        **source_citation,
    }


# ---------------------------------------------------------------------------
# Edge factory
# ---------------------------------------------------------------------------


def _make_edges(
    unit_slug: str,
    upgrade_id: str,
    links: list[tuple[str, str]],
    is_replace: bool,
) -> list[dict]:
    edges: list[dict] = [
        {"src": unit_slug, "dst": upgrade_id, "relation": EdgeType.HAS_UPGRADE, "properties": {}}
    ]
    rule_links = [(s, ct) for s, ct in links if ct != "armyListEntry"]
    mount_links = [(s, ct) for s, ct in links if ct == "armyListEntry"]

    for slug, _ in mount_links:
        edges.append(
            {"src": upgrade_id, "dst": slug, "relation": EdgeType.UNLOCKS_MOUNT, "properties": {}}
        )

    for i, (slug, _) in enumerate(rule_links):
        if is_replace and i == 0 and len(rule_links) >= 2:
            # First rule link in a replace item = the weapon being replaced
            edges.append(
                {
                    "src": upgrade_id,
                    "dst": slug,
                    "relation": EdgeType.REPLACES_WEAPON,
                    "properties": {},
                }
            )
        else:
            # Provisional — two-pass relabels to UNLOCKS_WEAPON or UNLOCKS_ITEM
            edges.append(
                {
                    "src": upgrade_id,
                    "dst": slug,
                    "relation": EdgeType.UNLOCKS_RULE,
                    "properties": {},
                }
            )

    return edges


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


def _budget_type(text: str, linked_slugs: list[str]) -> str:
    """Determine the budget upgrade_type from text and linked slugs."""
    for slug in linked_slugs:
        if slug in _BUDGET_SLUG_TO_TYPE:
            return _BUDGET_SLUG_TO_TYPE[slug]
    if _MAGIC_STANDARD_BUDGET_RE.search(text):
        return "magic_standard_budget"
    return "magic_item_budget"


def _budget_name(text: str, upgrade_type: str, links: list[tuple[str, str]]) -> str:
    label_map = {
        "magic_item_budget": "Magic Item Budget",
        "magic_standard_budget": "Magic Standard Budget",
        "vampiric_powers_budget": "Vampiric Powers Budget",
        "rune_budget": "Rune Budget",
    }
    base = label_map.get(upgrade_type, "Budget")
    m = _BUDGET_RE.search(text)
    pts = int(m.group(1)) if m else None
    return f"{base} ({pts} pts)" if pts else base


def _cost_and_unit(text: str) -> tuple[int | None, str | None]:
    """Extract (points_cost, cost_unit) from text."""
    m = _COST_RE.search(text)
    if not m:
        return None, None
    pts = int(m.group(1))
    per = (m.group(2) or "").lower()
    if per == "model":
        return pts, "per_model"
    if per == "unit":
        return pts, "per_unit"
    return pts, "flat"


def _derive_mount_name(text: str, links: list[tuple[str, str]]) -> str:
    for slug, ct in links:
        if ct == "armyListEntry":
            # Convert slug to title case name
            return slug.replace("-", " ").title()
    return text.strip()[:60]


def _derive_swap_name(text: str, links: list[tuple[str, str]]) -> str:
    """Derive a short name for a weapon-replace upgrade."""
    rule_links = [s for s, ct in links if ct != "armyListEntry"]
    if len(rule_links) >= 2:
        old = rule_links[0].replace("-", " ").title()
        new = rule_links[1].replace("-", " ").title()
        return f"Replace {old} with {new}"
    if rule_links:
        return rule_links[0].replace("-", " ").title()
    return text.strip()[:60]


def _derive_generic_name(text: str, links: list[tuple[str, str]]) -> str:
    """Best-effort name for catch-all rule_add upgrades."""
    for slug, ct in links:
        if ct != "armyListEntry":
            return slug.replace("-", " ").title()
    return text.strip()[:60]


def _match_profile_scope(text: str, unit_slug: str, profile_slug_set: set[str]) -> str | None:
    """Return ``<unit_slug>#<profile_slug>`` if *text* starts with 'A <ProfileName> may'
    and the slugified profile name is in *profile_slug_set*.
    """
    m = _PROFILE_SCOPE_RE.match(text)
    if not m:
        return None
    raw_name = m.group(1).strip()
    profile_slug = _name_to_slug(raw_name)
    full_id = f"{unit_slug}#{profile_slug}"
    if full_id in profile_slug_set:
        return full_id
    return None


# ---------------------------------------------------------------------------
# Rich-text helpers (standalone, not instance methods)
# ---------------------------------------------------------------------------


def _first_unordered_list(node: dict) -> dict | None:
    for child in node.get("content", []):
        if child.get("nodeType") == "unordered-list":
            return child
    return None


def _nested_unordered_list(list_item: dict) -> dict | None:
    for child in list_item.get("content", []):
        if child.get("nodeType") == "unordered-list":
            return child
    return None


def _list_items(list_node: dict) -> list[dict]:
    return [c for c in list_node.get("content", []) if c.get("nodeType") == "list-item"]


def _paragraph_text(list_item: dict) -> str:
    """Return concatenated plain text from the first paragraph child of a list-item."""
    for child in list_item.get("content", []):
        if child.get("nodeType") == "paragraph":
            return _extract_text(child)
    return ""


def _extract_text(node: dict | None) -> str:
    if not isinstance(node, dict):
        return ""
    if node.get("nodeType") == "text":
        return node.get("value", "")
    return "".join(_extract_text(c) for c in node.get("content", []))


def _entry_links(node: dict | None) -> list[tuple[str, str]]:
    """Collect all (slug, contentType) pairs from entry-hyperlink nodes recursively."""
    if not isinstance(node, dict):
        return []
    results: list[tuple[str, str]] = []
    if node.get("nodeType") in ("entry-hyperlink", "embedded-entry-inline"):
        target = node.get("data", {}).get("target", {})
        slug = target.get("fields", {}).get("slug")
        ct = target.get("sys", {}).get("contentType", {}).get("sys", {}).get("id", "")
        if slug:
            results.append((slug, ct))
    for child in node.get("content", []):
        results.extend(_entry_links(child))
    return results


def _name_to_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
