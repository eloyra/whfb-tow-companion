"""
Parser for unit profile pages (``/unit/{slug}``).

Data source: ``__NEXT_DATA__.props.pageProps.entry`` (Contentful ``armyListEntry``).

All unit data — including stat profiles — is present directly on the unit page.
No cross-referencing with the army page is required.

Output nodes: one ``Unit`` node per page.
Output edges:
- ``BELONGS_TO``        — unit → army slug (from ``association`` field).
- ``HAS_TYPE``          — unit → troop type slug (from ``troopType`` field).
- ``HAS_RULE``          — unit → each special rule slug found in ``specialRules``.
- ``HAS_WEAPON``        — unit → weapon slug (from ``equipment`` richtext entry-hyperlinks).
- ``CAN_MOUNT``         — unit → mount unit slug (``armyListEntry`` links in ``options``).
- ``HAS_OPTIONAL_RULE`` — unit → optional rule slugs from ``optionalRules`` and rule-type
                          links in ``options`` (deduplicated).
- ``USES_LORE``         — unit → lore slug for each entry in ``magicLore`` (wizards only).

Field notes:
- ``unitCategory[0].fields`` gives the broad unit category (Cavalry, Infantry…)
  and distinguishes named characters (slug == "named-character").
- ``wizardLevel`` (int) and ``armourValue`` (str, e.g. "4+") are direct fields.
- ``association`` holds the army link; ``armyLists`` is always empty in this CMS.
- ``army_category`` maps the unitCategory slug to the army-list display label
  where determinable; it is ``null`` for generic unit types (Cavalry, Infantry…)
  whose list slot (Core/Special/Rare) is not captured at unit level.
"""

from __future__ import annotations

import logging

from pipeline.constants import TROOP_TYPE_SLUG_MAP, EdgeType, NodeType
from pipeline.scraper.parsers.base_parser import BaseParser, ParseResult

logger = logging.getLogger(__name__)

# unitCategory slug → army list display label (only for unambiguous mappings).
_ARMY_CATEGORY_MAP: dict[str, str] = {
    "named-character": "Named Characters",
    "character": "Characters",
    "mount": "Mounts",
}


class UnitParser(BaseParser):
    """Parse a unit profile page (armyListEntry) into a ``Unit`` node."""

    def parse(self, html: str, url: str, fetched_at: str) -> ParseResult:
        result = ParseResult()
        pp = self._extract_next_data(html)
        if pp is None:
            logger.warning("UnitParser: ISR fallback or missing data at %s", url)
            return result

        entry = pp.get("entry", {})
        if not entry:
            logger.warning("UnitParser: no entry in pageProps at %s", url)
            return result

        ct = entry.get("sys", {}).get("contentType", {}).get("sys", {}).get("id")
        if ct != "armyListEntry":
            logger.warning("UnitParser: unexpected contentType %r at %s", ct, url)
            return result

        fields = entry.get("fields", {})
        name: str = fields.get("name", "")
        slug: str = fields.get("slug") or self._slug(url)
        date = self._date_only(fetched_at)

        # Stat profiles
        profiles = self._parse_unit_profiles(fields.get("unitProfile", []))

        # Troop type (specific subtype, e.g. "heavy-cavalry").
        # CMS slugs are sometimes singular; normalise to the plural URL slug used as node ID.
        troop_type_entry = self._first_linked(fields.get("troopType"))
        _raw_tt: str | None = troop_type_entry.get("slug") if troop_type_entry else None
        troop_type_id: str | None = TROOP_TYPE_SLUG_MAP.get(_raw_tt, _raw_tt) if _raw_tt else None

        # Unit category (broad type, e.g. "Cavalry") — also source of army_category
        # and is_named_character.
        unit_cat_entry = self._first_linked(fields.get("unitCategory"))
        unit_category: str | None = unit_cat_entry.get("name") if unit_cat_entry else None
        unit_cat_slug: str = unit_cat_entry.get("slug", "") if unit_cat_entry else ""
        is_named_character: bool = unit_cat_slug == "named-character"
        army_category: str | None = _ARMY_CATEGORY_MAP.get(unit_cat_slug)

        # Army membership via association (armyLists is always empty in this CMS).
        army_slugs: list[str] = [
            a.get("fields", {}).get("slug")
            for a in (fields.get("association") or [])
            if isinstance(a, dict) and a.get("fields", {}).get("slug")
        ]
        army_name = ""
        if army_slugs:
            army_name = (fields.get("association") or [{}])[0].get("fields", {}).get("name", "")

        # Wizard properties
        wizard_level: int | None = fields.get("wizardLevel")

        # Intrinsic armour value (e.g. "4+" for monsters with scaly skin)
        av_intrinsic: str | None = fields.get("armourValue") or None

        sc = self._make_source_citation(army_name or "Unknown Army")
        node = {
            "node_type": NodeType.UNIT,
            "id": slug,
            "url": url,
            **sc,
            "last_updated": date,
            "cost_points_per_model": fields.get("cost"),
            "unit_category": unit_category,
            "troop_type_id": troop_type_id,
            "army_category": army_category,
            "is_named_character": is_named_character,
            "wizard_level": wizard_level,
            "av_intrinsic": av_intrinsic,
            **self._parse_base_size(fields.get("baseSize", "")),
            **self._parse_unit_size(str(fields.get("unitSize", "1"))),
            "name": name,
            **self._make_i18n(name=name),
        }
        result.nodes.append(node)

        # Emit :Profile child nodes + HAS_PROFILE edges.
        # Profiles are first-class graph nodes so stats can be queried directly
        # via Cypher (e.g. units with WS≥5 and A≥3 across any sub-profile).
        for order, profile in enumerate(profiles):
            profile_name = profile.get("name") or f"profile-{order}"
            profile_id = f"{slug}#{self._name_to_slug(profile_name)}"
            result.nodes.append(
                {
                    "node_type": NodeType.PROFILE,
                    "id": profile_id,
                    "url": url,
                    **sc,
                    "name": profile_name,
                    "M": profile.get("M"),
                    "WS": profile.get("WS"),
                    "BS": profile.get("BS"),
                    "S": profile.get("S"),
                    "T": profile.get("T"),
                    "W": profile.get("W"),
                    "I": profile.get("I"),
                    "A": profile.get("A"),
                    "Ld": profile.get("Ld"),
                    "order": order,
                }
            )
            result.edges.append(
                self._make_edge(slug, profile_id, EdgeType.HAS_PROFILE, {"order": order})
            )

        # BELONGS_TO edges
        for army_slug in army_slugs:
            result.edges.append(self._make_edge(slug, army_slug, EdgeType.BELONGS_TO))

        # HAS_TYPE edge — unit → troop type node
        if troop_type_id:
            result.edges.append(self._make_edge(slug, troop_type_id, EdgeType.HAS_TYPE))

        # HAS_RULE edges — prefer linked slugs from entry-hyperlinks; fall back to
        # plain-text rule names converted to slugs.
        sr_links = self._richtext_entry_links(fields.get("specialRules"))
        sr_slugs_seen: set[str] = set()
        for link_slug in sr_links:
            if link_slug not in sr_slugs_seen:
                result.edges.append(self._make_edge(slug, link_slug, EdgeType.HAS_RULE))
                sr_slugs_seen.add(link_slug)

        if not sr_links:
            sr_text = self._richtext_to_text(fields.get("specialRules"))
            for rule_name in [line.strip() for line in sr_text.splitlines() if line.strip()]:
                rule_slug = self._name_to_slug(rule_name)
                if rule_slug not in sr_slugs_seen:
                    result.edges.append(self._make_edge(slug, rule_slug, EdgeType.HAS_RULE))
                    sr_slugs_seen.add(rule_slug)

        # HAS_WEAPON edges — standard equipment linked via richtext entry-hyperlinks
        for eq_slug, _ in self._richtext_entry_links_typed(fields.get("equipment")):
            result.edges.append(self._make_edge(slug, eq_slug, EdgeType.HAS_WEAPON))

        # CAN_MOUNT and HAS_OPTIONAL_RULE edges from the options field.
        # options contains: armyListEntry links (mounts) and rule links
        # (optional weapons, rules, items — indistinguishable without cross-referencing).
        opt_seen: set[str] = set(sr_slugs_seen)  # dedup against already-emitted rules
        for opt_slug, ct in self._richtext_entry_links_typed(fields.get("options")):
            if ct == "armyListEntry":
                result.edges.append(self._make_edge(slug, opt_slug, EdgeType.CAN_MOUNT))
            elif opt_slug not in opt_seen:
                result.edges.append(self._make_edge(slug, opt_slug, EdgeType.HAS_OPTIONAL_RULE))
                opt_seen.add(opt_slug)

        # HAS_OPTIONAL_RULE edges from dedicated optionalRules field
        for link_slug in self._richtext_entry_links(fields.get("optionalRules")):
            if link_slug not in opt_seen:
                result.edges.append(self._make_edge(slug, link_slug, EdgeType.HAS_OPTIONAL_RULE))
                opt_seen.add(link_slug)

        # USES_LORE edges — wizard units only.
        # magicLore field slugs have a "-lore" suffix (e.g. "battle-magic-lore") that
        # does not match Lore node IDs (e.g. "battle-magic"); strip it before emitting.
        for lore_entry in fields.get("magicLore") or []:
            lore_slug = (
                lore_entry.get("fields", {}).get("slug") if isinstance(lore_entry, dict) else None
            )
            if lore_slug:
                lore_slug = lore_slug.removesuffix("-lore")
                result.edges.append(self._make_edge(slug, lore_slug, EdgeType.USES_LORE))

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _first_linked(self, val: object) -> dict:
        """Return the ``fields`` dict of the first item in a linked-entry list."""
        if isinstance(val, list) and val:
            return val[0].get("fields") or {}
        if isinstance(val, dict):
            return val.get("fields") or {}
        return {}
