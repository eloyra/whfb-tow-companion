# Graph Validation Tracker

> **VERSION:** 1.0 | **Items:** 52 | **Pending:** 52 | **Done:** 0
> Last updated: 2026-05-29

---

## How to run a validation pass (READ FIRST)

You validate **EXACTLY ONE item** per run. Do not start a second item.

1. Read this whole file AND `docs/warhammer_tow_domain_knowledge.md` for full context.
2. In the **Item Index** below, pick the **FIRST item whose box is unchecked** `- [ ]`
   (top to bottom). That is your item. Do not pick any other.
3. Jump to that item's detail block (same ID). Read Producer / Data / Authoritative / Known flags.
4. Validate ONLY that item. Run BOTH:
   - **Structural conformity**: read the named parser source + named `data/parsed/` file(s) +
     the schema section + relevant ADR. Confirm required fields exist with correct types,
     ids are unique slugs, edges resolve to real node ids, no orphans/dangling.
   - **Domain coverage**: using the domain doc, confirm the Warhammer concept is fully captured
     (all 19 armies, all listed troop types, weapon S-modifiers, spell types, etc.).
   - Optional: query Neo4j if it is running; otherwise rely on `data/graph/load_report.json`.
5. **DO NOT** modify pipeline code, parsers, schema, ADRs, or data. This task is read-only
   except for writing your conformity report and updating this tracker's two status markers.
6. Write a conformity report at `docs/validation/conformity/<ID>-<slug>.md` using the
   **Conformity Report Template** below. Be concrete: cite file paths, counts, sample
   records/edges, any Cypher queries run.
7. Mark the item done: change its `- [ ]` to `- [x]` in the Item Index, set its detail
   block `Status: PENDING` → `Status: DONE`, and add `Report: <relative path>`.
8. **Stop.** Report which item you validated and the verdict. Do not begin another item.

If every box is already checked, report "all items validated" and stop.

---

## Conformity Report Template

Copy this into `docs/validation/conformity/<ID>-<slug>.md`:

```markdown
# Conformity Report — <ID>: <Title>

- Item: <ID>
- Date: <YYYY-MM-DD>
- Validator: <model/agent>
- Verdict: PASS | PASS WITH GAPS | FAIL

## Scope
What this node/edge represents in Warhammer, and exactly what was checked.

## What works
- ...

## What is missing
- ...

## What could be improved
- ...

## Evidence
Files inspected (paths), counts observed, sample records/edges, queries run.

## Recommendations (non-binding — for a future fix pass)
- ...
```

---

## Item Index

- [ ] F01 — Parse output shape & edge-record contract
- [ ] F02 — i18n strategy (`{field}_es`, drop of `i18n` dict)
- [ ] F03 — Scalar flattening (`source_citation`, `base_size_mm`, `unit_size`)
- [ ] F04 — Node-ID conventions & uniqueness
- [ ] F05 — Schema-doc ⇄ constants ⇄ data drift reconciliation
- [ ] F06 — Loader integrity & derived/seeded edges
- [ ] N01 — Army node
- [ ] N02 — Unit node
- [ ] N03 — Profile node
- [ ] N04 — TroopType node
- [ ] N05 — SpecialRule node
- [ ] N06 — CoreRule node
- [ ] N07 — Document node
- [ ] N08 — Terrain node
- [ ] N09 — Lore node
- [ ] N10 — Spell node
- [ ] N11 — Weapon node
- [ ] N12 — MagicItem node
- [ ] N13 — Upgrade node
- [ ] N14 — CompositionList node
- [ ] N15 — CompositionSlot node
- [ ] N16 — FAQ node
- [ ] N17 — Errata node
- [ ] E01 — BELONGS_TO
- [ ] E02 — HAS_TYPE
- [ ] E03 — HAS_PROFILE
- [ ] E04 — SPLIT_PROFILE_OF
- [ ] E05 — HAS_RULE
- [ ] E06 — HAS_OPTIONAL_RULE
- [ ] E07 — HAS_WEAPON
- [ ] E08 — CAN_MOUNT
- [ ] E09 — CAN_TAKE_ITEM
- [ ] E10 — USES_LORE
- [ ] E11 — BELONGS_TO_LORE
- [ ] E12 — PART_OF_SECTION
- [ ] E13 — HAS_UPGRADE
- [ ] E14 — UNLOCKS_RULE
- [ ] E15 — UNLOCKS_WEAPON
- [ ] E16 — UNLOCKS_ITEM
- [ ] E17 — UNLOCKS_MOUNT
- [ ] E18 — REPLACES_WEAPON
- [ ] E19 — HAS_LIST
- [ ] E20 — HAS_SLOT
- [ ] E21 — SLOT_ALLOWS
- [ ] E22 — ALLIED_WITH
- [ ] E23 — HAS_COMPOSITION_RULE
- [ ] E24 — REFERENCES
- [ ] E25 — HAS_INTRINSIC_RULE
- [ ] E26 — CLARIFIES
- [ ] E27 — AMENDS
- [ ] E28 — TERRAIN_INTERACTION (defined, unproduced — gap validation)
- [ ] E29 — HAS_OPTIONAL_WEAPON (defined, unproduced — gap validation)

---

## Foundation Items

---

### F01 — Parse output shape & edge-record contract

```
Status: PENDING
Report: —
Domain: n/a — cross-cutting contract; correct shape is prerequisite for every entity item.
Source: ADR-0004-parse-output-contract.md (binding); pipeline/CLAUDE.md (may be stale).
Producer: pipeline/scraper/parsers/__init__.py (coordinator writes final JSON).
Authoritative: docs/decisions/ADR-0004-parse-output-contract.md · pipeline/CLAUDE.md.
Data: data/parsed/*.json (17 node files + edges.json).
Structural checks:
  - Each data/parsed/*.json is a top-level JSON ARRAY (not {nodes:[],edges:[]} object).
  - Edge records use keys: src, dst, relation, properties — NOT source/target/edge_type.
  - pipeline/CLAUDE.md edge-shape prose says source/target/edge_type — confirm this is stale
    and the actual data uses src/dst/relation/properties (ADR-0004 form).
  - pipeline/CLAUDE.md node-shape prose shows nested source_citation and i18n — confirm
    actual data has FLAT scalars (source_citation_book, source_citation_page, name_es etc.).
  - Every edge record has exactly these four keys; properties is {} when empty, not absent.
  - Node records carry no embedded node_type/label field (type is implicit in filename).
Domain checks: n/a (contract item).
Known flags:
  - CONTRADICTION: pipeline/CLAUDE.md describes {nodes:[],edges:[]} per-file shape; ADR-0004
    and actual data use flat-array-per-file. ADR-0004 is binding; CLAUDE.md prose is stale.
  - CONTRADICTION: edge keys in CLAUDE.md (source/target/edge_type) vs data (src/dst/relation).
    Confirm which wins; check if builder.py or loader.py rekey anywhere.
Conformity doc: docs/validation/conformity/F01-parse-output-shape.md
```

---

### F02 — i18n strategy (`{field}_es`, drop of `i18n` dict)

```
Status: PENDING
Report: —
Domain: n/a — i18n plumbing; affects every node type.
Source: ADR-0004 amendment (2026-04-24) · ADR-0005.
Producer: pipeline/scraper/parsers/base_parser.py (_make_i18n method).
Authoritative: ADR-0004 amendment · ADR-0005 §i18n.
Data: any data/parsed/*.json (sample 5 node types for coverage).
Structural checks:
  - No node record contains a nested i18n dict key.
  - Spanish translations stored as {field}_es scalars (name_es, text_es) when present.
  - _make_i18n in base_parser.py currently returns {} — confirm Spanish fields are absent
    from current data (populated only after translation stage).
  - English content lives in plain name/text top-level keys.
  - No node record contains i18n, translations, or locale keys.
Domain checks: n/a.
Known flags:
  - _make_i18n returns {} currently; Spanish columns absent from parsed data. This is expected
    pre-translation-stage behaviour — confirm it is intentional and documented.
  - ADR-0005 instructs frontend: coalesce(n.name_es, n.name). Verify no node has name_es
    without name (would break fallback).
Conformity doc: docs/validation/conformity/F02-i18n-strategy.md
```

---

### F03 — Scalar flattening (`source_citation`, `base_size_mm`, `unit_size`)

```
Status: PENDING
Report: —
Domain: n/a — ADR-0004 amendment flattening contract.
Source: ADR-0004 amendment (2026-04-24).
Producer: pipeline/scraper/parsers/base_parser.py (and unit_parser.py for unit-specific fields).
Authoritative: ADR-0004 amendment.
Data: data/parsed/units.json (most affected) · any node file for source_citation.
Structural checks:
  - Every node record has source_citation_book (str|None) and source_citation_page (str|None).
    No nested source_citation:{book,page} object present.
  - Unit records have base_width_mm (int|None) and base_depth_mm (int|None).
    No nested base_size_mm:{width,depth} object.
  - Unit records have unit_size_min (int|None) and unit_size_max (int|None).
    No nested unit_size:{min,max} object.
  - Verify at least 5 node types (e.g. Army, SpecialRule, CoreRule, Spell, Weapon) have
    source_citation_book/page as flat scalars.
Domain checks: n/a.
Known flags: none — flattening is believed complete and consistent.
Conformity doc: docs/validation/conformity/F03-scalar-flattening.md
```

---

### F04 — Node-ID conventions & uniqueness

```
Status: PENDING
Report: —
Domain: n/a — ADR-0005 id conventions underpin all graph MERGE operations.
Source: ADR-0005-graph-storage-conventions.md.
Producer: all parsers (id assignment); pipeline/scraper/parsers/base_parser.py (slug utility).
Authoritative: ADR-0005 §node-id.
Data: all 17 data/parsed/*.json files.
Structural checks:
  - Standard nodes: id = URL slug (e.g. "blood-knights", "fear"). No spaces, no uppercase.
  - Profile nodes: id = "{unit-slug}#{profile-name-slug}" (e.g. "blood-knights#kastellan").
  - Upgrade nodes: id = "{unit-slug}#upgrade-{n}" (integer sequence per unit).
  - CompositionList: id = "{army-slug}#composition-list".
  - CompositionSlot: id = "{army-slug}#composition-list#{slot-name-slug}".
  - Uniqueness: within each file, no duplicate id values.
  - Cross-file: ids intended to be globally unique across all node types (check for
    accidental collisions between e.g. a TroopType slug and a SpecialRule slug).
  - Edge src/dst values all resolve to an id that exists in some node file.
Domain checks: n/a.
Known flags:
  - load_report.json orphan_missing_src_count: 3 — identify those 3 edges and their src ids.
  - Upgrade id scheme uses integer sequence per unit — confirm no two upgrades on the same
    unit share the same n.
Conformity doc: docs/validation/conformity/F04-node-id-conventions.md
```

---

### F05 — Schema-doc ⇄ constants ⇄ data drift reconciliation

```
Status: PENDING
Report: —
Domain: n/a — contract integrity; underpins every entity item.
Source: docs/schema/knowledge_graph_schema.md · pipeline/constants.py · data/parsed/edges.json.
Producer: n/a.
Authoritative: schema doc is the named authority; ADR-0005 amendment for Upgrade/Composition.
Data: edges.json (27 distinct relations) · constants NodeType/EdgeType enums.
Structural checks:
  - Every NodeType label (17) has a section in the schema doc.
    Flag: Profile, CompositionList, CompositionSlot — present in constants, ABSENT from schema body.
  - Every EdgeType defined in constants (27+) appears in data OR has a documented justification.
    Flag: HAS_OPTIONAL_WEAPON — 0 emitters; HAS_UNIT — in schema but not in constants/data.
  - HAS_OPTIONAL_RULE present in data (1272 edges) but MISSING from schema doc edge tables.
  - HAS_UNIT listed in schema doc structural table but absent from constants.py and data — phantom.
  - Upgrade properties in schema doc :Upgrade vs ADR-0005 amendment vs upgrades.json column set:
    list every divergence (schema stale; ADR-0005 adds points_budget, mutex_group,
    applies_to_profile, availability_constraint, bsb_unlimited_magic_standard, order).
  - EMBEDDABLE_LABELS in constants.py adds Terrain (13 labels); ADR-0005 §6 lists 12 (no Terrain).
    Flag and justify.
  - alliance_type vocabulary: schema says trusted|uneasy|suspicious; domain doc says
    trusted/suspicious/desperate. Confirm which string the data uses and reconcile.
Domain checks: n/a.
Known flags: all six bullet-point flags above are expected findings — verify each still holds,
  quantify where possible, and state whether each is a schema doc gap or a constants gap.
Conformity doc: docs/validation/conformity/F05-schema-constants-data-drift.md
```

---

### F06 — Loader integrity & derived/seeded edges

```
Status: PENDING
Report: —
Domain: n/a — graph build quality; the graph is what the RAG queries at runtime.
Source: data/graph/load_report.json · pipeline/graph/builder.py · pipeline/graph/seeds.py.
Producer: pipeline/graph/loader.py (MERGE) · builder.py (derives) · seeds.py (seeds).
Authoritative: ADR-0005 §loader; load_report.json as ground truth for what was built.
Data: data/graph/load_report.json (all 17 node counts + 27 edge counts).
Structural checks:
  - All node expected==actual (delta 0). Confirm for all 17 labels.
  - warnings: [] and threshold_errors: [] — confirm still empty.
  - edge_drops: {} — confirm no edges dropped during load.
  - orphan_missing_src_count: 3 — identify the 3 orphan edges; judge severity.
  - Derived edges: CAN_TAKE_ITEM raw=10 → built=69942 (builder._derive_can_take_item).
    Confirm derivation logic is correct: Unit→Upgrade→BELONGS_TO army→army magic items.
  - Seeded edges: ALLIED_WITH 44 (seeds.py). TERRAIN_INTERACTION seeded but count=0 or absent
    from load_report edge_counts — confirm status and whether this is a known issue.
  - Count deltas between edges.json and load_report (e.g. REFERENCES 4715→6031; CAN_TAKE_ITEM
    10→69942): identify source of each significant delta.
  - null_army_id_unreachable_item_count: 11 — identify which items have null army_id and why.
  - armies_without_can_take_item_count: 1 — identify which army lacks CAN_TAKE_ITEM edges.
Domain checks: n/a.
Known flags:
  - TERRAIN_INTERACTION "enabled but unverified" per pipeline/CLAUDE.md Fix 5. Check if any
    TERRAIN_INTERACTION edges exist in the built graph or if seed list is effectively empty.
  - Builder derives CAN_TAKE_ITEM via 3 Cypher MERGE passes; 69942 edges is very large —
    sanity-check the derivation scope (should be Unit→MagicItem from same army, not all-vs-all).
Conformity doc: docs/validation/conformity/F06-loader-integrity.md
```

---

## Node Items

---

### N01 — Army node  (`:Army`, `NodeType.ARMY`)

```
Status: PENDING
Report: —
Domain: §12 Armies (Factions), §5 Army Composition. Army = one playable faction.
Source: /army/{slug}, Contentful contentType `association`.
Producer: pipeline/scraper/parsers/army_parser.py.
Authoritative: docs/schema/knowledge_graph_schema.md :Army · constants NodeType.ARMY.
Data: data/parsed/armies.json (19) · load_report Army expected==actual==19.
Structural checks:
  - 19 records exactly — one per playable army.
  - Required fields present: id (slug), url, source_citation_book, source_citation_page,
    last_updated, name.
  - id is lowercase slug (e.g. "vampire-counts", "empire-of-man").
  - No nested objects (source_citation flattened per F03; no i18n dict per F02).
  - Schema lists composition_percentages as an Army property — confirm whether it is absent
    (moved to CompositionList/CompositionSlot) or still present on the node.
Domain checks:
  - All 19 armies from domain doc §12 are present. Expected slugs:
    beastmen-brayherds, chaos-dwarfs, daemons-of-chaos, dark-elves,
    dwarfen-mountain-holds, empire-of-man, grand-cathay, high-elf-realms,
    kingdom-of-bretonnia, lizardmen, ogre-kingdoms, orc-and-goblin-tribes,
    realms-of-men, regiments-of-renown, skaven, tomb-kings-of-khemri,
    vampire-counts, warriors-of-chaos, wood-elf-realms.
  - No duplicate army names.
  - name field is human-readable (e.g. "Vampire Counts", not "vampire-counts").
Known flags: none specific; schema lists composition_percentages as Army property but
  composition data moved to CompositionList/CompositionSlot in ADR-0005 — check if field
  still present or removed.
Conformity doc: docs/validation/conformity/N01-army.md
```

---

### N02 — Unit node  (`:Unit`, `NodeType.UNIT`)

```
Status: PENDING
Report: —
Domain: §4 Troop Types, §5 Composition, §6 Characters, §8 Equipment. Unit = one army-list entry.
Source: /unit/{slug}, Contentful contentType `armyListEntry`.
Producer: pipeline/scraper/parsers/unit_parser.py (+ _options.py for upgrades).
Authoritative: schema doc :Unit · constants NodeType.UNIT · ADR-0004 (profiles externalised)
  · ADR-0005 (id=slug).
Data: data/parsed/units.json (574) · load_report Unit expected==actual==574.
Structural checks:
  - Required fields present and typed:
    cost_points_per_model (int|None), unit_category (str), troop_type_id (str|None),
    army_category (str), is_named_character (bool), wizard_level (int|None),
    av_intrinsic (str|None), base_width_mm (int|None), base_depth_mm (int|None),
    unit_size_min (int|None), unit_size_max (int|None), name (str).
  - No embedded profiles[] array — must be externalised to profiles.json + HAS_PROFILE edges.
  - troop_type_id resolves to a TroopType id (load_report dangling_troop_type_id_count=0).
  - id = URL slug, unique across all 574 records.
  - army_category values within expected set: Core, Special, Rare, Characters, Mounts, Allies,
    Mercenaries (or similar).
Domain checks:
  - All 19 armies have at least one unit (check BELONGS_TO distribution).
  - Categories cover Characters / Core / Special / Rare / Mounts;
    is_named_character=True for named characters (e.g. Vlad von Carstein).
  - Mounted/complex units have multiple profiles linked via HAS_PROFILE + SPLIT_PROFILE_OF.
  - Wizard units have wizard_level set (1–4); non-wizard units have wizard_level=None.
Known flags:
  - 1 unit has unit_category=None — identify the offending unit and judge whether valid or bug.
  - 574 units vs 19 armies = ~30 per army avg; check no army has 0 units.
Conformity doc: docs/validation/conformity/N02-unit.md
```

---

### N03 — Profile node  (`:Profile`, `NodeType.PROFILE`)

```
Status: PENDING
Report: —
Domain: §3.1 Characteristics (M/WS/BS/S/T/W/I/A/Ld). Profile = one stat row for a unit
  or unit component (rider, mount, chariot crew, etc.).
Source: embedded in unit pages (armyListEntry unitProfile array).
Producer: pipeline/scraper/parsers/unit_parser.py.
Authoritative: ADR-0004 amendment (profiles externalised) · ADR-0005 §Profile id convention
  · constants NodeType.PROFILE. NOTE: schema doc body has NO :Profile section — it was added
  only in ADR-0004/0005 amendments.
Data: data/parsed/profiles.json (945) · load_report Profile expected==actual==945.
Structural checks:
  - id format: "{unit-slug}#{profile-name-slug}" (e.g. "blood-knights#kastellan").
  - Required fields: id, name, order (int), M/WS/BS/S/T/W/I/A/Ld each int|None.
  - No stat field is a string; dash/missing values must be None not "-" or 0.
  - order is non-negative int, unique within profiles of the same unit.
  - 945 profiles for 574 units = ~1.6 profiles/unit; multi-profile units account for delta.
  - Verify that profile ids embed the correct parent unit slug (split on "#" → first part
    must exist as a unit id in units.json).
Domain checks:
  - CHARACTERISTIC_MAP keys (M,WS,BS,S,T,W,I,A,Ld) are the 9 valid stat columns — no others.
  - Monstrous/multi-profile units (e.g. chariot, dragon-rider) have ≥2 profiles each.
  - Stat ranges are plausible: M 1–12, WS 1–10, BS 0–10, S 1–10, T 1–10, W 1–6 typical
    (monsters higher); flag any outlier > 10 for manual check.
Known flags:
  - Profile node absent from schema doc body — this is a known schema-doc gap, not a data bug.
  - Some profiles may have all stats None (e.g. a war machine with no crew stats shown) —
    check if any profile has M=None AND WS=None AND all stats None (fully-null profile).
Conformity doc: docs/validation/conformity/N03-profile.md
```

---

### N04 — TroopType node  (`:TroopType`, `NodeType.TROOP_TYPE`)

```
Status: PENDING
Report: —
Domain: §4 Troop Types — the foundational unit classification (Infantry, Cavalry, Monster etc.).
  Determines rank bonus, unit strength, AV cap, intrinsic rules.
Source: /troop-types-in-detail/{slug}, Contentful contentType `rule`.
Producer: pipeline/scraper/parsers/rule_parser.py (URL-branched on `/troop-types-in-detail/`).
Authoritative: schema doc :TroopType · constants NodeType.TROOP_TYPE · TROOP_TYPE_SEED in
  constants.py (seeds min_models_for_rank_bonus, max_rank_bonus, unit_strength_per_model).
Data: data/parsed/troop_types.json (40) · load_report TroopType expected==actual==40.
Structural checks:
  - Required fields: id, url, name, text, category, min_models_for_rank_bonus (int|None),
    max_rank_bonus (int|None), unit_strength_per_model (int|None).
  - TROOP_TYPE_SEED in constants.py seeds numeric values for the 13 canonical types —
    confirm seeded rows have non-None values for all three numeric fields.
  - 40 entries: 13 canonical + sub-pages/variant pages. Identify which are canonical vs variant.
  - category values: infantry, cavalry, beast, chariot, monster, war_machine, swarm, unknown.
    Flag: 19 of 40 have category=unknown — check if these are variant pages or parsing gaps.
Domain checks:
  - Domain doc §4 table lists 13 troop types. Verify all 13 are present as records:
    Infantry, Monstrous Infantry, Heavy Infantry, Cavalry, Heavy Cavalry, Monstrous Cavalry,
    War Beasts, Monstrous Beasts, Light Chariots, Heavy Chariots, Swarms, Monsters, War Machines.
  - min_models_for_rank_bonus matches domain table (e.g. Infantry=5, Cavalry=3).
  - max_rank_bonus matches domain table (e.g. Infantry=3, Cavalry=2, Monsters=0).
  - unit_strength_per_model matches domain table (e.g. Infantry=1, Cavalry=2).
Known flags:
  - 19 of 40 have category=unknown — likely variant/sub-pages; identify and flag.
  - TROOP_TYPE_SEED seeds values not in the wiki page content (they are game constants);
    confirm seed lookup is applied correctly for each canonical type slug.
Conformity doc: docs/validation/conformity/N04-troop-type.md
```

---

### N05 — SpecialRule node  (`:SpecialRule`, `NodeType.SPECIAL_RULE`)

```
Status: PENDING
Report: —
Domain: §9 Special Rules — universal (any army) or army-specific abilities that modify
  core rules. Examples: Fear, Terror, Killing Blow, Regeneration, Frenzy.
Source: /special-rules/{slug}, Contentful contentType `rule`.
Producer: pipeline/scraper/parsers/rule_parser.py.
Authoritative: schema doc :SpecialRule · constants NodeType.SPECIAL_RULE.
Data: data/parsed/special_rules.json (643) · load_report SpecialRule expected==actual==643.
Structural checks:
  - Required fields: id, url, name, text, rule_scope (universal|army), army_id (str|None).
  - rule_scope=universal → army_id must be None.
  - rule_scope=army → army_id must be a valid army slug.
  - 83 universal + 560 army-specific = 643 total — confirm counts.
  - text is non-empty for all records (rules with no text are a data gap).
  - id is the rule slug (e.g. "fear", "killing-blow").
Domain checks:
  - Domain doc §9 lists key universal rules. Spot-check presence of:
    Fly, Skirmishers, Scouts, Vanguard, Ambushers, Fast Cavalry, Strider, Swiftstride,
    Unstable, Killing Blow, Heroic Killing Blow, Armour Bane, Multiple Wounds, Impact Hits,
    Stomp, Thunderstomp, Frenzy, Hatred, Stubborn, Unbreakable, Immune to Psychology,
    Regeneration, Ward Save, Fear, Terror, Stupidity, Flammable, Flaming Attacks,
    Poisoned Attacks, Large Target, Ethereal, Undead, Breath Weapon, Magic Resistance,
    Scaly Skin, Strength in Numbers.
  - All 19 armies have army-specific rules (check army_id distribution).
  - rule_scope inferred correctly from URL (no army prefix = universal; army prefix = army).
Known flags: none specific.
Conformity doc: docs/validation/conformity/N05-special-rule.md
```

---

### N06 — CoreRule node  (`:CoreRule`, `NodeType.CORE_RULE`)

```
Status: PENDING
Report: —
Domain: §2 Turn Sequence, §3 Core Mechanics — the rulebook mechanics that govern all play.
  Also includes army-list composition text (emitted by ArmyListParser).
Source: core rulebook mechanic pages (various paths); /warhammer-armies/*-army-list pages.
Producer: pipeline/scraper/parsers/core_rule_parser.py · pipeline/scraper/parsers/army_list_parser.py.
Authoritative: schema doc :CoreRule · constants NodeType.CORE_RULE.
Data: data/parsed/core_rules.json (1377) · load_report CoreRule expected==actual==1377.
Structural checks:
  - Required fields: id, url, name, text, section (str), section_id (str),
    prev_page_url (str|None), next_page_url (str|None).
  - text is non-empty for all records.
  - section values are URL path segments (e.g. "magic", "close-combat", "movement").
  - prev_page_url / next_page_url are valid URLs or None (not empty strings).
  - Army-list composition nodes (17) are included in this count — check section values
    for army-list nodes (expected "warhammer-armies" or similar).
Domain checks:
  - Core game sections from domain doc §2–§3 are represented:
    movement, shooting, magic, close-combat, turn-sequence, characteristics, psychology.
  - Each section has a navigable chain (prev/next links form a sequence, not orphan nodes).
  - 1377 nodes for rulebook text — spot-check 3 core mechanics for completeness of text.
Known flags: ArmyListParser also emits CoreRule for army-list composition pages (17 nodes).
  Confirm these 17 are identifiable by their section or id pattern.
Conformity doc: docs/validation/conformity/N06-core-rule.md
```

---

### N07 — Document node  (`:Document`, `NodeType.DOCUMENT`)

```
Status: PENDING
Report: —
Domain: Non-mechanic textual pages (army lore, background, narrative content) that are
  valuable as context but not game-rule mechanics.
Source: document-type pages (classified via DOCUMENT_SECTIONS / DOCUMENT_PAGES in constants).
Producer: pipeline/scraper/parsers/core_rule_parser.py (CoreRuleParser, document branch).
Authoritative: schema doc :Document · constants NodeType.DOCUMENT · DOCUMENT_SECTIONS /
  DOCUMENT_PAGES constants.
Data: data/parsed/documents.json (37) · load_report Document expected==actual==37.
Structural checks:
  - Required fields: id, url, name, text, section (str), section_id (str),
    prev_page_url (str|None), next_page_url (str|None).
  - Document emits NO edges (CoreRuleParser document branch emits none).
  - 37 records — identify the page types classified as documents vs core rules.
  - text is non-empty for all records.
Domain checks:
  - Verify the classification boundary: lore/background pages → Document; mechanics → CoreRule.
  - Spot-check 3 Document records — confirm none are actually game-mechanic content
    (misclassification would mean graph queries miss them).
Known flags: CoreRuleParser uses DOCUMENT_SECTIONS/DOCUMENT_PAGES from constants.py to
  classify; check if the boundary matches the schema doc intention.
Conformity doc: docs/validation/conformity/N07-document.md
```

---

### N08 — Terrain node  (`:Terrain`, `NodeType.TERRAIN`)

```
Status: PENDING
Report: —
Domain: §10 Terrain — 9 primary terrain categories + special features and buildings.
  Terrain affects movement, shooting, combat, and grants/denies cover.
Source: battlefield-terrain pages (Contentful `rule`, ruleType `battlefield-terrain`).
Producer: pipeline/scraper/parsers/terrain_parser.py.
Authoritative: schema doc :Terrain · constants NodeType.TERRAIN.
Data: data/parsed/terrains.json (37) · load_report Terrain expected==actual==37.
Structural checks:
  - Required fields: id, url, name, text, terrain_class, movement_penalty (str|None),
    blocks_movement (bool|None), disrupts_units (bool|None),
    requires_dangerous_test (bool|None), grants_cover (None|"partial"|"full"),
    special_feature_benefit (str|None).
  - terrain_class values: open, difficult, dangerous, impassable, low_linear_obstacle,
    high_linear_obstacle, woods, hills, special_feature, building, linear_terrain_feature.
  - 8 records have terrain_class=None — identify these; judge parsing gap vs valid.
  - TerrainParser emits NO edges (TERRAIN_INTERACTION seeded separately — see E28).
  - grants_cover constrained to None/"partial"/"full" only.
Domain checks:
  - Domain doc §10 table lists 9+ terrain types. Confirm nodes for:
    Open Ground, Difficult Terrain, Dangerous Terrain, Impassable Terrain,
    Low Linear Obstacle, High Linear Obstacle, Woods, Hills, Buildings, Special Features.
  - movement_penalty, disrupts_units, requires_dangerous_test, grants_cover match domain
    table values for at least 5 terrain types.
  - 37 total vs ~9 canonical types: extra records are sub-pages/variant terrain pages.
Known flags:
  - 8 records with terrain_class=None — could be classification misses in the parser.
  - TERRAIN_INTERACTION edges (seeded, not parsed) are validated separately in E28.
  - EMBEDDABLE_LABELS adds Terrain; ADR-0005 embeddable list does not include it (F05 flag).
Conformity doc: docs/validation/conformity/N08-terrain.md
```

---

### N09 — Lore node  (`:Lore`, `NodeType.LORE`)

```
Status: PENDING
Report: —
Domain: §7.1 Lores of Magic — thematic spell collections (7 spells each: 1 signature + 6
  numbered). Universal lores available to multiple armies; army-specific lores exclusive.
Source: /the-lores-of-magic/{slug}, Contentful contentType varies.
Producer: pipeline/scraper/parsers/lore_parser.py.
Authoritative: schema doc :Lore · constants NodeType.LORE.
Data: data/parsed/lores.json (38) · load_report Lore expected==actual==38.
Structural checks:
  - Required fields: id, url, name, text, source_citation_book, source_citation_page, last_updated.
  - id is lore slug (e.g. "battle-magic", "lore-of-beasts").
  - 38 lores — more than the ~8 universal lores in domain doc; army-specific lores account
    for the delta.
  - text contains spell names (used by coordinator two-pass for renegade lore linking).
Domain checks:
  - Universal lores from domain doc §7.1 present: Battle Magic, Elementalism, High Magic,
    Dark Magic, Necromancy, Waaagh! Magic, Little Waaagh!, Feral Instincts (and others).
  - Army-specific lores present for all 19 armies that use magic (confirm Dwarfs have none
    — they use Runes, not Lores).
  - Each lore expected to have ~7 linked Spell nodes via BELONGS_TO_LORE edges (see E11).
    Check if any lore has 0 linked spells.
Known flags:
  - Renegade lores (spells not embedded in standard lore page) rely on coordinator two-pass
    name-matching for BELONGS_TO_LORE — some spells may be unlinked. Quantify.
  - 38 lores × 7 spells = ~266 expected; only 139 spells parsed and 151 BELONGS_TO_LORE edges
    exist — significant gap. Investigate if spells are parsed on separate /spell/ pages only
    or also embedded in lore pages.
Conformity doc: docs/validation/conformity/N09-lore.md
```

---

### N10 — Spell node  (`:Spell`, `NodeType.SPELL`)

```
Status: PENDING
Report: —
Domain: §7.3 Spell Types — spells cast during the Magic Phase. 7 types: Magic Missile, Hex,
  Enchantment, Conveyance, Assailment, Magical Vortex, Bound Spell.
Source: /spell/{slug}, Contentful contentType `spell`.
Producer: pipeline/scraper/parsers/spell_parser.py.
Authoritative: schema doc :Spell · constants NodeType.SPELL.
Data: data/parsed/spells.json (139) · load_report Spell expected==actual==139.
Structural checks:
  - Required fields: id, url, name, text, lore_id (str|None), lore_number (int|None, 0–6),
    casting_value (int|None), casting_value_override (str|None),
    casting_value_boosted (None — always None currently), range (str|None),
    spell_type (str|None), duration (None), target (None).
  - lore_number=0 → signature spell; 1–6 → numbered spell.
  - spell_type observed values: Assailment, Magic Missile, Hex, Magical Vortex, Conveyance,
    Enchantment. Confirm "Bound Spell" and "Remains in Play" (RiP) are absent from spell_type
    (likely described in text rather than parsed as a type field).
  - spell_type extracted from rendered DOM div.spell Type row — confirm all 139 have a
    non-None spell_type or explain expected nulls.
  - duration and target are always None — confirm and flag as known gap vs schema spec.
Domain checks:
  - Domain doc §7.3 lists 7 spell types; 6 observed. Check if any Bound Spell pages exist
    as /spell/ pages or are only described in CoreRules.
  - casting_value plausible range: 5–15 typical; flag outliers.
  - lore_id links to a valid lore id in lores.json (for the 139 spells with a known lore).
Known flags:
  - casting_value_boosted always None — schema says it should be int|None for spells with
    boosted casting values (e.g. "Casting Value: 7+ / 10+"). Flag as parsing gap.
  - duration and target always None — schema expects these for timing/targeting metadata.
  - spell_type extracted from DOM (not CMS JSON) — fragile; verify extraction correct.
Conformity doc: docs/validation/conformity/N10-spell.md
```

---

### N11 — Weapon node  (`:Weapon`, `NodeType.WEAPON`)

```
Status: PENDING
Report: —
Domain: §8 Equipment, Weapons, and Armour — melee weapons, missile weapons, armour,
  war machine weapons. Key stats: weapon_class, range, strength modifier, AP.
Source: /weapons-of-war/{slug}, Contentful `rule`, ruleType `weapons-of-war`.
Producer: pipeline/scraper/parsers/weapon_parser.py.
Authoritative: schema doc :Weapon · constants NodeType.WEAPON.
Data: data/parsed/weapons.json (264) · load_report Weapon expected==actual==264.
Structural checks:
  - Required fields: id, url, name, text, weapon_class, range (str|None), strength (str|None),
    ap (str|None), special_rules (list[str]|None), armour_value (None), shots (None),
    template_type (None), is_indirect (None), bounce (None).
  - weapon_class values: melee (31), missile (16), armour (11), equipment (206), war_machine (0).
  - War-machine-specific fields (shots, template_type, is_indirect, bounce) always None —
    flag as known gap; domain §8.4 lists cannon bounce, stone thrower template, etc.
  - armour_value always None — schema spec has it; confirm parsing gap.
  - special_rules extracted from DOM table.profile-table--weapon — check parse quality.
  - 206 "equipment" class is very large — investigate what is classified as equipment vs
    melee/missile (e.g. are shields, barding classified as equipment?).
Domain checks:
  - Domain doc §8.1 lists key melee weapons. Spot-check presence of:
    hand-weapon, great-weapon, halberd, lance, spear, flail, additional-hand-weapon.
  - Domain doc §8.2 lists missile weapons. Spot-check: bow, crossbow, handgun, pistol.
  - Domain doc §8.3 lists armour: light-armour, heavy-armour, full-plate-armour, shield,
    barding. Verify these appear as weapon_class=armour records.
  - strength values match domain table (e.g. Great Weapon = S+2, Lance = S+2 on charge).
Known flags:
  - armour_value always None — schema spec implies it should hold AV for armour-class weapons.
  - shots/template_type/is_indirect/bounce always None — war machine profile data gap.
  - 206 "equipment" records — likely umbrella class for items that don't fit melee/missile/armour.
Conformity doc: docs/validation/conformity/N11-weapon.md
```

---

### N12 — MagicItem node  (`:MagicItem`, `NodeType.MAGIC_ITEM`)

```
Status: PENDING
Report: —
Domain: §11 Magic Items — purchasable equipment for characters. Types: Magic Weapon,
  Magic Armour, Talisman, Enchanted Item, Arcane Item, Magic Standard. Army-specific
  variants (Vampiric Powers, Gifts of Chaos, Daemonic Gifts).
Source: /magic-items/{slug}, Contentful `rule`, ruleType `magic-items` / `magic-items-and-abilities`.
Producer: pipeline/scraper/parsers/magic_item_parser.py.
Authoritative: schema doc :MagicItem · constants NodeType.MAGIC_ITEM.
Data: data/parsed/magic_items.json (698) · load_report MagicItem expected==actual==698.
Structural checks:
  - Required fields: id, url, name, text, item_type, points_cost (int|None), army_id (str|None),
    is_single_use (None — always None currently).
  - item_type values observed: magic_weapon (138), magic_armour (67), talisman (63),
    magic_standard (128), enchanted_item (82), arcane_item (82), ability (125), unique (13).
  - army_id: None for universal items; army slug for army-specific items.
  - MagicItemParser emits ZERO edges — no GRANTS_RULE edges emitted.
  - is_single_use always None — schema says bool|None; confirm parsing gap.
  - points_cost is int|None — check for any non-numeric strings or 0-cost items.
Domain checks:
  - Domain doc §11 lists 6 standard item types; data has 8 (adds ability + unique).
    Confirm ability maps to army-specific powers (Vampiric Powers, Gifts of Chaos).
  - All 19 armies that have army-specific items have army_id-matched records.
  - Universal items (army_id=None) are the shared magic item lists.
  - 125 ability items — confirm these are e.g. Vampiric Powers for Vampire Counts.
  - Magic Standards (128) — check points_cost range (should be ≤100 pts typically).
Known flags:
  - is_single_use always None — "Unique" items per domain doc are limited to 1 per army;
    this uniqueness constraint is not captured in the data.
  - MagicItem emits 0 edges from parser — no GRANTS_RULE, no CAN_TAKE_ITEM from item side.
    Links via Unit→MagicItem are derived by builder (see E09).
  - 13 "unique" item_type records — check if these are Named Characters' special items.
Conformity doc: docs/validation/conformity/N12-magic-item.md
```

---

### N13 — Upgrade node  (`:Upgrade`, `NodeType.UPGRADE`)

```
Status: PENDING
Report: —
Domain: §5.2 Composition, §6 Characters — purchasable options on units: command groups
  (champion/musician/standard), weapon upgrades, mount options, magic item budgets,
  wizard level upgrades.
Source: unit options rich-text (embedded in armyListEntry pages) + army-list BSB entries.
Producer: pipeline/scraper/parsers/_options.py (via UnitParser) +
  pipeline/scraper/parsers/army_list_parser.py (BSB upgrades).
Authoritative: schema doc :Upgrade (note: stale — ADR-0005 amendment supersedes) ·
  constants NodeType.UPGRADE · ADR-0005 amendment.
Data: data/parsed/upgrades.json (2424) · load_report Upgrade expected==actual==2424.
Structural checks:
  - Required fields per ADR-0005 amendment: id, url, name, description, upgrade_type,
    points_cost (int|None), cost_unit (str|None), points_budget (int|None),
    mutex_group (str|None), applies_to_profile (str|None),
    availability_constraint (str|None), replaces_weapon_id (str|None),
    bsb_unlimited_magic_standard (bool|None), order (int).
  - upgrade_type values: command_bsb (21), weapon_add (638), rule_add (421), rune_budget (29),
    magic_item_budget (257), mount (281), wizard_level (47), armour_add (123),
    command_champion (166), command_standard (132), command_musician (136),
    magic_standard_budget (88), weapon_replace (81), vampiric_powers_budget (4).
    Total must equal 2424.
  - id format: "{unit-slug}#upgrade-{n}"; n is unique per unit.
  - Schema doc :Upgrade is stale vs ADR-0005 — confirm actual data columns match ADR-0005 fields.
Domain checks:
  - Domain doc §5.2 mentions Champions, Musicians, Standard Bearers for command groups.
    Confirm command_champion + command_musician + command_standard + command_bsb coverage.
  - Magic item budget upgrades (257) should link characters to their magic item allowance.
  - Wizard level upgrades (47) — check points_cost plausibility (e.g. 35 pts per level).
  - vampiric_powers_budget (4) — very low; check if Vampire Counts units are covered.
Known flags:
  - Schema doc :Upgrade lists champion_magic_allowance, champion_power_allowance (old names);
    ADR-0005 replaces these with points_budget, mutex_group etc. Flag which columns actually
    exist in upgrades.json.
  - vampiric_powers_budget only 4 records — may be too few for VC coverage.
Conformity doc: docs/validation/conformity/N13-upgrade.md
```

---

### N14 — CompositionList node  (`:CompositionList`, `NodeType.COMPOSITION_LIST`)

```
Status: PENDING
Report: —
Domain: §5.2 Percentage Categories — the container holding an army's percentage-category
  slots (Characters/Core/Special/Rare/Allies). One per army.
Source: /warhammer-armies/<army>-army-list pages (heading-level sections).
Producer: pipeline/scraper/parsers/army_list_parser.py.
Authoritative: ADR-0005 amendment :CompositionList · constants NodeType.COMPOSITION_LIST.
  NOTE: NOT in schema doc body — schema-doc gap confirmed in F05.
Data: data/parsed/composition_lists.json (17) · load_report CompositionList expected==actual==17.
Structural checks:
  - 17 records — one per army with a parsed army-list page.
    NOTE: 19 armies exist but only 17 CompositionLists — identify which 2 armies are missing
    and whether this is expected (e.g. Regiments of Renown / Realms of Men may lack standard
    composition pages).
  - Required fields: id ("{army-slug}#composition-list"), army_id (str), url.
  - army_id resolves to a valid Army id in armies.json.
  - id uniquely identifies each list.
Domain checks:
  - Each CompositionList should have ≥4 CompositionSlot children (Characters/Core/Special/Rare).
  - Check if Allies slot exists for armies that allow allied contingents (§5.3).
Known flags:
  - 17 vs 19 armies — 2 armies lack CompositionLists. Flag which ones; check if their
    army-list pages exist on the wiki or were not scraped.
  - CompositionList absent from schema doc body; present in constants + ADR-0005.
Conformity doc: docs/validation/conformity/N14-composition-list.md
```

---

### N15 — CompositionSlot node  (`:CompositionSlot`, `NodeType.COMPOSITION_SLOT`)

```
Status: PENDING
Report: —
Domain: §5.2 Percentage Categories — one slot per category (Core min 25%, Rare max 25%,
  Special max 50%, Characters max 50%, Allies max 25%). Slots define the legal budget range.
Source: /warhammer-armies/<army>-army-list pages (heading-level sections).
Producer: pipeline/scraper/parsers/army_list_parser.py.
Authoritative: ADR-0005 amendment :CompositionSlot · constants NodeType.COMPOSITION_SLOT.
  NOTE: NOT in schema doc body — schema-doc gap confirmed in F05.
Data: data/parsed/composition_slots.json (83) · load_report CompositionSlot expected==actual==83.
Structural checks:
  - Required fields: id, composition_list_id (str), army_id (str), slot_name (str),
    min_pct (int|None), max_pct (int|None).
  - 83 slots / 17 lists = avg 4.9 slots per army.
  - composition_list_id resolves to a CompositionList id.
  - min_pct / max_pct values consistent with domain §5.2 table:
    Core: min=25, max=None; Special: min=None, max=50; Rare: min=None, max=25;
    Characters: min=None, max=50; Allies: min=None, max=25.
  - slot_name values expected: Characters, Core, Special, Rare, Allies, Mercenaries, BSB.
Domain checks:
  - Every CompositionList should have a Core slot with min_pct=25 (mandatory 25% minimum).
  - Armies of Infamy may have modified slots — check if any slot has unusual min/max.
  - min_pct=None and max_pct=None simultaneously would be a data gap — flag any such records.
Known flags:
  - 83 / 17 = 4.9 avg — some armies have extra slots (e.g. Mercenaries, BSB sections).
  - CompositionSlot absent from schema doc body; present in constants + ADR-0005.
Conformity doc: docs/validation/conformity/N15-composition-slot.md
```

---

### N16 — FAQ node  (`:FAQ`, `NodeType.FAQ`)

```
Status: PENDING
Report: —
Domain: Official FAQ entries — clarifications on rules ambiguities. Each FAQ entry has
  a question and an answer referencing one or more rules.
Source: /faq (and /faq/<section>), pageProps.entries[] array.
Producer: pipeline/scraper/parsers/faq_parser.py.
Authoritative: schema doc :FAQ · constants NodeType.FAQ.
Data: data/parsed/faqs.json (244) · load_report FAQ expected==actual==244.
Structural checks:
  - Required fields: id, url, name, topic (str), source_document (str), source_version (str),
    question (str), answer (str).
  - question and answer non-empty for all records.
  - topic derived from URL suffix (e.g. section name); may be None for top-level FAQ page.
  - id is a slug derived from the question text.
  - No duplicate question texts within same source_document.
Domain checks:
  - 244 FAQs — check distribution by source_document (should span multiple books/army FAQs).
  - CLARIFIES edge coverage: 203 of 244 have CLARIFIES edges (83.2%). Check the 41 without
    links — are they unlinked due to parsing failure or genuinely unresolvable?
  - answer text is complete (not truncated) — spot-check 3 entries.
Known flags:
  - 41 FAQs with no CLARIFIES edges — may need improved name-matching in coordinator two-pass.
  - load_report faq_with_clarifies: 203 (83.2%) — confirm this matches edges.json CLARIFIES
    count (source=FAQ nodes).
Conformity doc: docs/validation/conformity/N16-faq.md
```

---

### N17 — Errata node  (`:Errata`, `NodeType.ERRATA`)

```
Status: PENDING
Report: —
Domain: Official errata — corrections to published rules. Each entry identifies the original
  text and the corrected replacement.
Source: /errata, pageProps.entries[] array.
Producer: pipeline/scraper/parsers/errata_parser.py.
Authoritative: schema doc :Errata · constants NodeType.ERRATA.
Data: data/parsed/errata.json (210) · load_report Errata expected==actual==210.
Structural checks:
  - Required fields: id, url, name, source_document (str), source_version (str),
    original_text (None — always None currently), corrected_text (str).
  - corrected_text non-empty for all records.
  - original_text always None — schema says str|None; flag as parsing gap (CMS doesn't
    surface original text separately).
  - name field is page-prefix-stripped rule name (e.g. "supreme-matriarch-of-nan-gau").
Domain checks:
  - AMENDS edge coverage: 185 of 210 have AMENDS edges (88.1%). Check the 25 without links.
  - source_document distribution — should span multiple books/army supplements.
  - corrected_text is complete — spot-check 3 entries; confirm not truncated.
Known flags:
  - original_text always None — the schema specifies it; this is a known CMS-data limitation.
    The corrected_text alone is less useful for comparison (reader can't see what changed).
  - 25 errata with no AMENDS edges — investigate if name-matching could be improved.
Conformity doc: docs/validation/conformity/N17-errata.md
```

---

## Edge / Relation Items

---

### E01 — BELONGS_TO  (`:Unit`→`:Army`)

```
Status: PENDING
Report: —
Domain: Every unit belongs to one army (faction). §5 Composition, §12 Armies.
  Note: phantom inverse HAS_UNIT (Army→Unit) was listed in schema doc but never implemented.
Source: unit pages (association field) + army parser (unitsByType list).
Producer: unit_parser.py (primary) · army_parser.py (cross-emits for unitsByType).
Authoritative: schema doc BELONGS_TO · constants EdgeType.BELONGS_TO.
Data: edges.json BELONGS_TO count=584 · load_report BELONGS_TO=595 (delta 11 builder-derived).
Structural checks:
  - src resolves to a Unit id; dst resolves to an Army id.
  - 584 in edges.json vs 574 units — 10 units appear in multiple BELONGS_TO edges
    (e.g. Regiments of Renown units belonging to multiple armies). Identify and validate.
  - No unit with 0 BELONGS_TO edges (every unit must belong to at least one army).
  - Phantom HAS_UNIT: confirm it does NOT appear in edges.json or load_report (schema ghost).
Domain checks:
  - Distribution: all 19 armies should be dst targets with ≥1 edge.
  - Regiments of Renown / mercenary units may legitimately have multiple BELONGS_TO edges —
    confirm this is by design.
Known flags:
  - 584 > 574 units: multi-army membership. Determine which units and which armies.
  - load_report delta +11: source of extra 11 BELONGS_TO in built graph vs edges.json.
  - HAS_UNIT phantom: schema doc lists Army→Unit edge; confirm absent from constants/data.
Conformity doc: docs/validation/conformity/E01-belongs-to.md
```

---

### E02 — HAS_TYPE  (`:Unit`→`:TroopType`)

```
Status: PENDING
Report: —
Domain: Every unit has exactly one troop type (§4). Troop type determines rank bonus, US,
  AV cap, intrinsic rules.
Source: unit pages (troopType field), normalized via TROOP_TYPE_SLUG_MAP in unit_parser.py.
Producer: unit_parser.py.
Authoritative: schema doc HAS_TYPE · constants EdgeType.HAS_TYPE.
Data: edges.json HAS_TYPE count=570 · load_report HAS_TYPE=581 (delta 11).
Structural checks:
  - src resolves to a Unit id; dst resolves to a TroopType id.
  - 570 edges vs 574 units: 4 units have no HAS_TYPE edge. Identify them and determine cause.
  - Each unit should have at most 1 HAS_TYPE edge (verify no unit has 2+).
  - dst values are TroopType slugs — confirm they match troop_types.json ids.
  - TROOP_TYPE_SLUG_MAP normalizes wiki strings (e.g. "Light Cavalry" → canonical slug).
Domain checks:
  - All 13 canonical troop types (§4 table) appear as HAS_TYPE dst targets.
  - Distribution reasonable: Infantry most common, Monsters/Swarms rare.
  - Named characters typically share troop type with their unit (e.g. Vampire Lord =
    same as a regular Vampire Lord unit).
Known flags:
  - 4 units missing HAS_TYPE — check unit_parser.py TROOP_TYPE_SLUG_MAP for unmapped strings.
  - load_report delta +11: source unknown — builder may derive some HAS_TYPE.
Conformity doc: docs/validation/conformity/E02-has-type.md
```

---

### E03 — HAS_PROFILE  (`:Unit`→`:Profile`, property `order`)

```
Status: PENDING
Report: —
Domain: Each unit has ≥1 stat profile (§3.1 Characteristics). Complex units (rider+mount,
  chariot) have multiple profiles. order distinguishes them.
Source: unit pages (unitProfile array).
Producer: unit_parser.py.
Authoritative: schema doc HAS_PROFILE · constants EdgeType.HAS_PROFILE · ADR-0005 (order prop).
Data: edges.json HAS_PROFILE count=945 · load_report HAS_PROFILE=967 (delta 22).
Structural checks:
  - src resolves to a Unit id; dst resolves to a Profile id.
  - Edge carries properties={order: int} — confirm order is int, not None.
  - 945 edges == 945 Profile nodes (1:1 correspondence between profiles and HAS_PROFILE edges).
  - Each unit has ≥1 HAS_PROFILE edge (no unit with 0 profiles).
  - Multiple HAS_PROFILE edges from same unit have distinct order values.
Domain checks:
  - Single-profile units (infantry, most cavalry): 1 HAS_PROFILE edge.
  - Multi-profile units (chariots, dragon-riders, monster mounts): ≥2 edges.
  - Spot-check a known multi-profile unit (e.g. a mounted lord or chariot unit) to confirm
    all component profiles present.
Known flags:
  - load_report delta +22: 22 extra HAS_PROFILE in graph vs edges.json; investigate if builder
    derives any HAS_PROFILE or if this is a MERGE dedup artefact.
Conformity doc: docs/validation/conformity/E03-has-profile.md
```

---

### E04 — SPLIT_PROFILE_OF  (`:Profile`→`:Unit`, property `profile_role`)

```
Status: PENDING
Report: —
Domain: Links a mount/component profile back to its parent unit for split-profile units
  (rider + mount, chariot + crew + beasts). profile_role identifies the component.
Source: unit pages (unitProfile array, mount-sub-profile detection).
Producer: unit_parser.py (_is_mount_profile heuristic).
Authoritative: schema doc SPLIT_PROFILE_OF · constants EdgeType.SPLIT_PROFILE_OF.
Data: edges.json SPLIT_PROFILE_OF count=155 · load_report SPLIT_PROFILE_OF=155.
Structural checks:
  - src resolves to a Profile id; dst resolves to the parent Unit id.
  - Edge carries properties={profile_role: str} — value expected "mount" for current
    implementation.
  - 155 edges: 155 mount profiles linked back to their parent units.
  - Verify dst is the same unit as the HAS_PROFILE edge pointing to src
    (i.e. the profile belongs to the unit it points back to).
Domain checks:
  - Domain doc §3.1 describes split profiles for: rider+mount, chariot crew+chariot+beasts,
    war machine crew+machine. Current parser only covers mount sub-profiles.
  - Identify units with chariots or war-machine crew profiles — check if they have
    SPLIT_PROFILE_OF edges (pipeline/CLAUDE.md notes this as a known gap for non-mount splits).
  - profile_role="mount" for all 155 — confirm no chariot or war-machine profile_role emitted.
Known flags:
  - CLAUDE.md states SPLIT_PROFILE_OF emitted only for mount sub-profiles; chariot/war-machine
    splits are a known gap. Quantify how many expected chariot/WM units lack this edge.
  - If pipeline/CLAUDE.md says "not emitted" for non-mount splits but code emits mount-only,
    the doc is partially stale — record the discrepancy.
Conformity doc: docs/validation/conformity/E04-split-profile-of.md
```

---

### E05 — HAS_RULE  (`:Unit`/`:Army`→`:SpecialRule`)

```
Status: PENDING
Report: —
Domain: A unit's included special rules (always-on, not optional). §9 Special Rules.
  Also emitted from army nodes for army-wide rules.
Source: unit pages (specialRules field) + army pages (rulesByType section).
Producer: unit_parser.py · army_parser.py.
Authoritative: schema doc HAS_RULE · constants EdgeType.HAS_RULE.
Data: edges.json HAS_RULE count=4324 · load_report HAS_RULE=4395 (delta 71).
Structural checks:
  - src resolves to a Unit or Army id; dst resolves to a SpecialRule id.
  - 4324 edges across 574 units + 19 armies = ~7 rules/unit avg. Plausible.
  - No dangling dst (all SpecialRule ids exist in special_rules.json).
  - Distinct from HAS_OPTIONAL_RULE (E06) — HAS_RULE = always active; HAS_OPTIONAL_RULE =
    purchasable/conditional.
Domain checks:
  - Verify a known rule-heavy unit (e.g. Vampire Lord) has expected rules.
  - Universal rules (Fear, Undead, Immune to Psychology) linked via HAS_RULE to correct units.
  - Army-specific rules linked from Army node via HAS_RULE.
Known flags:
  - load_report delta +71: builder adds HAS_RULE for some reason; investigate.
  - Distinguish Army→SpecialRule (army-wide rules) from Unit→SpecialRule (unit rules) in count.
Conformity doc: docs/validation/conformity/E05-has-rule.md
```

---

### E06 — HAS_OPTIONAL_RULE  (`:Unit`→`:SpecialRule`)

```
Status: PENDING
Report: —
Domain: Rules a unit can gain by purchasing an upgrade option. Also currently covers
  optional weapons (HAS_OPTIONAL_WEAPON gap — weapons are lumped in here).
Source: unit pages (options rich-text links, optionalRules field).
Producer: unit_parser.py.
Authoritative: constants EdgeType.HAS_OPTIONAL_RULE. NOTE: ABSENT from schema doc —
  schema-doc gap confirmed in F05.
Data: edges.json HAS_OPTIONAL_RULE count=1272 · load_report HAS_OPTIONAL_RULE=1292 (delta 20).
Structural checks:
  - src resolves to a Unit id; dst resolves to a SpecialRule id (or in some cases a Weapon id —
    since HAS_OPTIONAL_WEAPON is not emitted, optional weapons may appear here as dst=weapon slug).
  - Verify dst types: what fraction point to SpecialRule vs Weapon vs other node types?
  - No edge here should duplicate a HAS_RULE edge for the same src-dst pair.
Domain checks:
  - Optional rule examples: units that can buy Frenzy, Hatred, Mark of Nurgle etc.
  - Confirm a known multi-option unit (e.g. Empire Wizard with upgrade options) has the
    expected optional rule links.
Known flags:
  - HAS_OPTIONAL_RULE absent from schema doc — this is the standing schema gap.
  - HAS_OPTIONAL_WEAPON defined in EdgeType constants but 0 emitters; optional weapons
    currently classified as optional rules. Validate how many dst values are weapon slugs.
  - E29 (HAS_OPTIONAL_WEAPON) validates the gap in detail.
Conformity doc: docs/validation/conformity/E06-has-optional-rule.md
```

---

### E07 — HAS_WEAPON  (`:Unit`/`:Army`→`:Weapon`)

```
Status: PENDING
Report: —
Domain: Weapons included in a unit's standard equipment (not optional). §8 Equipment.
Source: unit pages (equipment entry-links) + army pages (weapons-of-war section links).
Producer: unit_parser.py · army_parser.py.
Authoritative: schema doc HAS_WEAPON · constants EdgeType.HAS_WEAPON.
Data: edges.json HAS_WEAPON count=1549 · load_report HAS_WEAPON=1607 (delta 58).
Structural checks:
  - src resolves to a Unit or Army id; dst resolves to a Weapon id.
  - No dangling dst (all Weapon ids exist in weapons.json).
  - Distinct from HAS_OPTIONAL_RULE+optional weapons and UNLOCKS_WEAPON (upgrade path).
Domain checks:
  - Standard infantry has hand-weapon at minimum; cavalry has lance or sword.
  - Spot-check 3 known units (e.g. Grave Guard = great weapons; Empire Halberdiers = halberds).
  - Army nodes linked to their army-specific weapons pages.
Known flags:
  - load_report delta +58: source of extra edges in built graph vs edges.json.
Conformity doc: docs/validation/conformity/E07-has-weapon.md
```

---

### E08 — CAN_MOUNT  (`:Unit`→`:Unit`)

```
Status: PENDING
Report: —
Domain: Character units that can purchase a mount. src = character unit, dst = mount unit
  (itself a Unit node with unit_category="Mounts"). §6 Characters.
Source: unit pages (options rich-text containing mount armyListEntry links).
Producer: unit_parser.py.
Authoritative: schema doc CAN_MOUNT · constants EdgeType.CAN_MOUNT.
Data: edges.json CAN_MOUNT count=288 · load_report CAN_MOUNT=288.
Structural checks:
  - src resolves to a Unit id (character); dst resolves to a Unit id (mount).
  - dst unit should have unit_category="Mounts" — check compliance rate.
  - No self-loops (src != dst).
  - 288 mount options across characters — plausible given ~164 character units.
Domain checks:
  - Domain doc §6 lists common mounts: Warhorse, Barded Warhorse, Pegasus, Dragon, Griffon,
    Manticore, Nightmare. Spot-check a wizard/lord character for expected CAN_MOUNT edges.
  - Confirm that basic infantry characters (Heroes, Champions) may have fewer mount options
    than Lords.
Known flags: none specific.
Conformity doc: docs/validation/conformity/E08-can-mount.md
```

---

### E09 — CAN_TAKE_ITEM  (`:Army`→`:MagicItem` raw; `:Unit`→`:MagicItem` derived)

```
Status: PENDING
Report: —
Domain: Characters can purchase magic items within their budget. §11 Magic Items.
  Raw edges: army parser links army to magic-items page slug (not individual items).
  Derived edges: builder expands to Unit→individual MagicItem via upgrade budget logic.
Source: army pages (magic-items / magic-items-and-abilities section links).
Producer: army_parser.py (raw, 10 edges) · pipeline/graph/builder.py::_derive_can_take_item
  (derived, 69942 edges in built graph).
Authoritative: schema doc CAN_TAKE_ITEM (edge props: budget, via_upgrade; DERIVED, not in
  edges.json) · constants EdgeType.CAN_TAKE_ITEM · ADR-0005 amendment.
Data: edges.json CAN_TAKE_ITEM count=10 (raw) · load_report CAN_TAKE_ITEM=69942 (derived).
Structural checks:
  - Raw edges (10): src=Army id, dst=magic-items page slug. Confirm dst resolves to something
    (MagicItem id or CoreRule? — page slug may not be a MagicItem id).
  - Derived edges (69942): src=Unit id, dst=MagicItem id. Confirm scope of derivation:
    should be units belonging to the army × magic items available to that army.
  - 69942 = very large; sanity check derivation: ~574 units × ~698 items = max 400,852 —
    so 69942 is a subset. Verify builder scopes to army-matched items only.
  - ADR-0005 says edge props: budget (int), via_upgrade (bool). Confirm derived edges carry these.
Domain checks:
  - Army-specific items (army_id != None) only accessible by units of that army.
  - Universal items (army_id=None) accessible by all characters.
  - load_report armies_without_can_take_item_count: 1 — identify which army; check if it
    intentionally has no magic items (e.g. Dwarfs use Runes, not standard magic items).
Known flags:
  - Raw edges (10): likely army → magic-items landing page slug, not individual item slugs.
    These may be semantically weak links vs the 69942 derived Unit→MagicItem edges.
  - 69942 derived edges are a post-load artefact; not in edges.json. Validate builder logic.
  - 11 items have null_army_id that are considered unreachable — investigate.
Conformity doc: docs/validation/conformity/E09-can-take-item.md
```

---

### E10 — USES_LORE  (`:Unit`/`:Army`→`:Lore`)

```
Status: PENDING
Report: —
Domain: Wizard units and armies that can access a lore of magic. §7.1 Lores.
  Army nodes link to army-specific lores; wizard units link to their available lore(s).
Source: unit pages (magicLore field) + army pages (the-lores-of-magic section links).
Producer: unit_parser.py · army_parser.py.
Authoritative: schema doc USES_LORE · constants EdgeType.USES_LORE.
Data: edges.json USES_LORE count=234 · load_report USES_LORE=234.
Structural checks:
  - src resolves to a Unit or Army id; dst resolves to a Lore id.
  - Lore id exists in lores.json.
  - Wizard units (wizard_level > 0) should have ≥1 USES_LORE edge.
  - Non-wizard units should have 0 USES_LORE edges.
Domain checks:
  - Universal lores accessible to multiple armies — check that multiple Army nodes point to
    e.g. "battle-magic".
  - Dwarfs (no Lores, use Runes): verify 0 USES_LORE edges from dwarf units/army.
  - Army-specific lores (e.g. Necromancy for Vampire Counts) linked from VC army node.
Known flags: none specific.
Conformity doc: docs/validation/conformity/E10-uses-lore.md
```

---

### E11 — BELONGS_TO_LORE  (`:Spell`→`:Lore`)

```
Status: PENDING
Report: —
Domain: Each spell belongs to exactly one lore. §7.1 Lores; 7 spells per lore (1 signature
  + 6 numbered).
Source: lore pages (embedded spell links, standard lores) + coordinator two-pass (renegade lores).
Producer: lore_parser.py (standard) · pipeline/scraper/parsers/__init__.py two-pass (renegade).
Authoritative: schema doc BELONGS_TO_LORE · constants EdgeType.BELONGS_TO_LORE.
Data: edges.json BELONGS_TO_LORE count=151 · load_report BELONGS_TO_LORE=153 (delta 2).
Structural checks:
  - src resolves to a Spell id; dst resolves to a Lore id.
  - 151 edges for 139 spells: some spells have multiple BELONGS_TO_LORE edges (same spell
    in multiple lores) OR the count difference means some lore pages reference the same spell.
  - Each Spell node should have ≥1 BELONGS_TO_LORE edge — check for spells with 0 links.
  - lore_number 0 = signature spell (one per lore); 1–6 = numbered.
Domain checks:
  - 38 lores × 7 spells = 266 expected max; only 151 edges. Significant gap — investigate.
  - Check how many lores have 0 linked spells (expected: some army-specific lores with spells
    on separate /spell/ pages may rely on two-pass but fail to match).
  - Confirm lore_number distribution: each lore should have exactly 1 signature (0) and up to
    6 numbered spells.
Known flags:
  - Renegade lore spells rely on coordinator two-pass name-matching; likely cause of gap.
    Identify how many spells are unlinked (139 spells - ~151 edges indicates ~12 spells may
    link to multiple lores, or some spells are linked more than once).
  - lore_parser.py emits BELONGS_TO_LORE for standard lores only; two-pass fills renegade lores.
Conformity doc: docs/validation/conformity/E11-belongs-to-lore.md
```

---

### E12 — PART_OF_SECTION  (`:CoreRule`→`:CoreRule`)

```
Status: PENDING
Report: —
Domain: Section hierarchy within core rulebook. A page belongs to a section (e.g.
  "wizards" page is PART_OF_SECTION "magic" section). §2–§3.
Source: core rule pages (URL structure, prev/next nav).
Producer: core_rule_parser.py · army_list_parser.py.
Authoritative: schema doc PART_OF_SECTION · constants EdgeType.PART_OF_SECTION.
Data: edges.json PART_OF_SECTION count=76 · load_report PART_OF_SECTION=77 (delta 1).
Structural checks:
  - src and dst both resolve to CoreRule ids.
  - dst = section page (parent); src = sub-page (child).
  - 76 edges for 1377 CoreRules: only a small fraction of pages have explicit section links —
    many pages link to a section root. Check if this is expected (section roots don't
    have PART_OF_SECTION edges themselves).
Domain checks:
  - Core game sections present: movement, shooting, magic, close-combat, psychology, terrain.
  - Navigation chains intact: pages within a section form a linked sequence.
Known flags: load_report delta +1 — minor; investigate.
Conformity doc: docs/validation/conformity/E12-part-of-section.md
```

---

### E13 — HAS_UPGRADE  (`:Unit`→`:Upgrade`)

```
Status: PENDING
Report: —
Domain: Purchasable options available to a unit. §5.2, §6. Covers all upgrade types
  (weapons, command group, magic budgets, mounts, wizard levels).
Source: unit pages (options rich-text) + army-list pages (BSB entries).
Producer: pipeline/scraper/parsers/_options.py (via UnitParser) +
  pipeline/scraper/parsers/army_list_parser.py (BSB).
Authoritative: schema doc HAS_UPGRADE · constants EdgeType.HAS_UPGRADE.
Data: edges.json HAS_UPGRADE count=2424 · load_report HAS_UPGRADE=2433 (delta 9).
Structural checks:
  - src resolves to a Unit id; dst resolves to an Upgrade id.
  - 2424 edges == 2424 Upgrade nodes (1:1).
  - Each unit may have 0–N HAS_UPGRADE edges; some units (fixed equipment, no options) may
    have 0.
  - BSB upgrades: src = the character unit that can be BSB; check these are character units.
Domain checks:
  - Command group options (champion/musician/standard) present for eligible units.
  - Magic item budget upgrades present for character units.
  - Units with no purchasable options (e.g. Swarms) have 0 HAS_UPGRADE edges — confirm.
Known flags:
  - load_report delta +9: builder adds 9 HAS_UPGRADE for BSB or other derived logic.
Conformity doc: docs/validation/conformity/E13-has-upgrade.md
```

---

### E14 — UNLOCKS_RULE  (`:Upgrade`→`:SpecialRule`)

```
Status: PENDING
Report: —
Domain: An upgrade option unlocks a special rule (the rule becomes active when upgrade
  is purchased). Residual after coordinator relabels UNLOCKS_WEAPON/UNLOCKS_ITEM.
Source: unit options links (provisionally UNLOCKS_RULE; coordinator relabels to
  UNLOCKS_WEAPON or UNLOCKS_ITEM if dst is a weapon/item slug).
Producer: pipeline/scraper/parsers/_options.py (provisional) →
  pipeline/scraper/parsers/__init__.py coordinator two-pass (final).
Authoritative: schema doc UNLOCKS_RULE · constants EdgeType.UNLOCKS_RULE.
Data: edges.json UNLOCKS_RULE count=350 · load_report UNLOCKS_RULE=350.
Structural checks:
  - src resolves to an Upgrade id; dst resolves to a SpecialRule id.
  - Verify dst nodes are SpecialRule (not Weapon or MagicItem — those should have been
    relabeled by coordinator to UNLOCKS_WEAPON/UNLOCKS_ITEM).
  - Check for any dst that resolves to a Weapon or MagicItem id (relabeling bug).
Domain checks:
  - Sample 5 UNLOCKS_RULE edges; confirm the special rule is plausible for the upgrade
    context (e.g. buying "Hatred" rule via upgrade option).
Known flags:
  - Residual: after coordinator relabeling, remaining UNLOCKS_RULE should point only to
    SpecialRule nodes. Any pointing to Weapon/MagicItem = coordinator relabeling failure.
Conformity doc: docs/validation/conformity/E14-unlocks-rule.md
```

---

### E15 — UNLOCKS_WEAPON  (`:Upgrade`→`:Weapon`)

```
Status: PENDING
Report: —
Domain: An upgrade option unlocks a weapon option for the unit. Relabeled from provisional
  UNLOCKS_RULE by coordinator when dst slug matches a known weapon id.
Source: coordinator two-pass relabeling of provisional UNLOCKS_RULE edges.
Producer: pipeline/scraper/parsers/__init__.py coordinator two-pass.
Authoritative: schema doc UNLOCKS_WEAPON · constants EdgeType.UNLOCKS_WEAPON.
Data: edges.json UNLOCKS_WEAPON count=824 · load_report UNLOCKS_WEAPON=824.
Structural checks:
  - src resolves to an Upgrade id; dst resolves to a Weapon id.
  - 824 weapon-unlock edges — largest UNLOCKS_* type.
  - Verify dst nodes are Weapon (not SpecialRule or MagicItem).
  - Confirm relabeling was complete: no UNLOCKS_RULE edge should point to a Weapon dst.
Domain checks:
  - Sample 5 edges: confirm upgrade→weapon pairs are sensible (e.g. command musician option
    doesn't unlock a weapon; a weapons-swap option does).
  - upgrade_type for src Upgrade node should be weapon_add or weapon_replace for most.
Known flags:
  - Coordinator relabeling step is the production mechanism — no parser directly emits this.
    Any failure in slug-lookup would leave edges as UNLOCKS_RULE pointing to Weapon.
Conformity doc: docs/validation/conformity/E15-unlocks-weapon.md
```

---

### E16 — UNLOCKS_ITEM  (`:Upgrade`→`:MagicItem`)

```
Status: PENDING
Report: —
Domain: An upgrade option unlocks a specific magic item. Relabeled from provisional
  UNLOCKS_RULE by coordinator when dst slug matches a known magic item id.
Source: coordinator two-pass relabeling.
Producer: pipeline/scraper/parsers/__init__.py coordinator two-pass.
Authoritative: schema doc UNLOCKS_ITEM · constants EdgeType.UNLOCKS_ITEM.
Data: edges.json UNLOCKS_ITEM count=16 · load_report UNLOCKS_ITEM=32 (delta 16).
Structural checks:
  - src resolves to an Upgrade id; dst resolves to a MagicItem id.
  - 16 in edges.json — very low. Check if this is expected (most item access is via
    CAN_TAKE_ITEM + budget, not direct UNLOCKS_ITEM).
  - load_report delta +16: builder doubles this count — investigate derivation.
  - Verify dst nodes are MagicItem.
Domain checks:
  - UNLOCKS_ITEM expected for named/fixed items directly granted by upgrades (e.g.
    a specific character's signature weapon sold as a named upgrade).
  - 16 is plausible for named items; most item selection handled via budget + CAN_TAKE_ITEM.
Known flags:
  - load_report delta +16 is 100% increase — significant. Investigate which 16 extra edges
    the builder derives post-load.
Conformity doc: docs/validation/conformity/E16-unlocks-item.md
```

---

### E17 — UNLOCKS_MOUNT  (`:Upgrade`→`:Unit`)

```
Status: PENDING
Report: —
Domain: An upgrade option unlocks a specific mount for a character. Similar to CAN_MOUNT
  (Unit→Unit) but anchored to the Upgrade node for points-cost attribution.
Source: unit options rich-text containing armyListEntry mount links.
Producer: pipeline/scraper/parsers/_options.py.
Authoritative: schema doc UNLOCKS_MOUNT · constants EdgeType.UNLOCKS_MOUNT.
Data: edges.json UNLOCKS_MOUNT count=285 · load_report UNLOCKS_MOUNT=285.
Structural checks:
  - src resolves to an Upgrade id; dst resolves to a Unit id (mount unit).
  - dst Unit should have unit_category="Mounts" — verify compliance rate.
  - Corresponding CAN_MOUNT edge (Unit→Unit) should exist for same character → mount pair.
  - Upgrade upgrade_type should be "mount" for these edges.
Domain checks:
  - 285 mount upgrade options across character units — plausible.
  - Spot-check: a character with multiple mount options has one Upgrade per mount, each with
    UNLOCKS_MOUNT to the correct mount unit.
Known flags: none specific.
Conformity doc: docs/validation/conformity/E17-unlocks-mount.md
```

---

### E18 — REPLACES_WEAPON  (`:Upgrade`→`:Weapon`)

```
Status: PENDING
Report: —
Domain: A weapon-swap upgrade that replaces a default weapon with another. src = the upgrade
  option, dst = the weapon being replaced (not the replacement — the replacement is linked
  via UNLOCKS_WEAPON on the same upgrade or a sibling upgrade).
Source: unit options rich-text (weapon swap options).
Producer: pipeline/scraper/parsers/_options.py.
Authoritative: schema doc REPLACES_WEAPON · constants EdgeType.REPLACES_WEAPON.
Data: edges.json REPLACES_WEAPON count=69 · load_report REPLACES_WEAPON=69.
Structural checks:
  - src resolves to an Upgrade id; dst resolves to a Weapon id (the weapon being swapped out).
  - upgrade_type for src should be weapon_replace.
  - The same Upgrade should also have UNLOCKS_WEAPON pointing to the replacement weapon.
    Check this pairing for a sample of 5 REPLACES_WEAPON edges.
  - replaces_weapon_id on the Upgrade node should match dst.
Domain checks:
  - Weapon swaps are common in TOW (e.g. swap hand weapon for great weapon).
  - 69 total — plausible subset of weapon options.
Known flags: none specific.
Conformity doc: docs/validation/conformity/E18-replaces-weapon.md
```

---

### E19 — HAS_LIST  (`:Army`→`:CompositionList`)

```
Status: PENDING
Report: —
Domain: Links an army to its CompositionList node (army composition structure). §5.2.
Source: army-list pages.
Producer: pipeline/scraper/parsers/army_list_parser.py.
Authoritative: ADR-0005 amendment EdgeType HAS_LIST · constants EdgeType.HAS_LIST.
Data: edges.json HAS_LIST count=17 · load_report HAS_LIST=17.
Structural checks:
  - src resolves to an Army id; dst resolves to a CompositionList id.
  - Exactly 17 edges — one per CompositionList (one per army with a parsed army-list page).
  - dst id = "{army-slug}#composition-list" — verify format.
  - 19 armies but only 17 HAS_LIST edges — 2 armies lack this edge (see N14).
Domain checks:
  - The 2 armies without HAS_LIST: identify and determine if their army-list pages exist.
Known flags: 17 < 19 armies — known gap from N14.
Conformity doc: docs/validation/conformity/E19-has-list.md
```

---

### E20 — HAS_SLOT  (`:CompositionList`→`:CompositionSlot`)

```
Status: PENDING
Report: —
Domain: Links a CompositionList to each of its category slots. §5.2.
Source: army-list pages (heading-3 sections: Characters/Core/Special/Rare/Allies/etc.).
Producer: pipeline/scraper/parsers/army_list_parser.py.
Authoritative: ADR-0005 amendment EdgeType HAS_SLOT · constants EdgeType.HAS_SLOT.
Data: edges.json HAS_SLOT count=83 · load_report HAS_SLOT=83.
Structural checks:
  - src resolves to a CompositionList id; dst resolves to a CompositionSlot id.
  - 83 edges == 83 CompositionSlot nodes (1:1).
  - Each CompositionList src appears in the expected number of edges (4–6 per army).
Domain checks:
  - Minimum 4 slots per army (Characters/Core/Special/Rare); some have Allies, Mercenaries.
  - slot_name values cover the §5.2 category set.
Known flags: none specific.
Conformity doc: docs/validation/conformity/E20-has-slot.md
```

---

### E21 — SLOT_ALLOWS  (`:CompositionSlot`→`:Unit`, properties `max_count`, `per_points`)

```
Status: PENDING
Report: —
Domain: Links a composition slot to the units it allows. §5.2 — Core slot allows Core units,
  Rare slot allows Rare units. Optional props: max_count (e.g. 0–1 per army) and per_points
  (e.g. 1 per 1000 pts).
Source: army-list pages (unit list under each heading section).
Producer: pipeline/scraper/parsers/army_list_parser.py.
Authoritative: ADR-0005 amendment EdgeType SLOT_ALLOWS · constants EdgeType.SLOT_ALLOWS.
Data: edges.json SLOT_ALLOWS count=532 · load_report SLOT_ALLOWS=543 (delta 11).
Structural checks:
  - src resolves to a CompositionSlot id; dst resolves to a Unit id.
  - 532 edges across 83 slots = avg 6.4 units per slot. Plausible.
  - properties max_count (int|None) and per_points (int|None) present on edge records.
  - dst Unit ids exist in units.json.
Domain checks:
  - Core slot→Core units; Special slot→Special units; Rare slot→Rare units; Characters slot
    →Characters units. Check that army_category of dst Unit matches the slot_name.
  - Units listed under multiple slots (e.g. High Elf Sea Guard can be Core or Special) appear
    in multiple SLOT_ALLOWS edges from different slots.
Known flags:
  - load_report delta +11: builder adds 11 SLOT_ALLOWS; investigate source.
  - max_count=None for most slots; non-None values represent "0–1 per army" restrictions.
Conformity doc: docs/validation/conformity/E21-slot-allows.md
```

---

### E22 — ALLIED_WITH  (`:Army`→`:Army`, property `alliance_type`)

```
Status: PENDING
Report: —
Domain: Directed alliance relationship between armies. §5.3 Allied Contingents.
  Types: trusted, suspicious, desperate. Direction is asymmetric (A→B may differ from B→A).
Source: army-list pages (allied contingent sections) + pipeline/graph/seeds.py (seeded).
Producer: pipeline/scraper/parsers/army_list_parser.py · pipeline/graph/seeds.py.
Authoritative: schema doc ALLIED_WITH (alliance_type ∈ trusted|uneasy|suspicious) ·
  constants EdgeType.ALLIED_WITH.
Data: edges.json ALLIED_WITH count=44 · load_report ALLIED_WITH=44.
Structural checks:
  - src and dst both resolve to Army ids.
  - properties alliance_type present; values in {trusted, suspicious, uneasy}.
  - No self-loops (src != dst).
  - Directed: A→B with alliance_type X does not imply B→A with same type.
Domain checks:
  - Domain doc §5.3 defines three alliance types: Trusted, Suspicious, Desperate.
    Data uses "uneasy" where domain uses "desperate" — reconcile naming (is uneasy=desperate?).
  - 19 armies: maximum possible directed edges = 19×18=342; 44 suggests most armies are not
    allied with each other. Check if all alliance combinations from the wiki are captured.
  - Spot-check 2–3 known alliances (e.g. High Elves + Dwarfs historically = Trusted Allies).
Known flags:
  - alliance_type default in parser is "trusted" when unspecified — confirm this doesn't
    silently mask missing alliance data.
  - "uneasy" (data) vs "desperate" (domain doc) naming mismatch — document which is canonical.
  - seeds.py contributes some ALLIED_WITH; parser contributes others. Confirm no duplicates
    between the two sources.
Conformity doc: docs/validation/conformity/E22-allied-with.md
```

---

### E23 — HAS_COMPOSITION_RULE  (`:Army`→`:CoreRule`)

```
Status: PENDING
Report: —
Domain: Links an army to the CoreRule node holding its full army-list composition text.
  The CoreRule captures the narrative text of the composition page. §5.
Source: army-list pages.
Producer: pipeline/scraper/parsers/army_list_parser.py.
Authoritative: schema doc HAS_COMPOSITION_RULE · constants EdgeType.HAS_COMPOSITION_RULE.
Data: edges.json HAS_COMPOSITION_RULE count=17 · load_report HAS_COMPOSITION_RULE=17.
Structural checks:
  - src resolves to an Army id; dst resolves to a CoreRule id.
  - 17 edges == 17 CompositionLists (same 17 armies with parsed army-list pages).
  - dst CoreRule id is the army-list page slug (e.g. "beastmen-brayherds-army-list").
  - Each CoreRule dst has section reflecting the army-list section.
Domain checks:
  - CoreRule text contains army composition rules (percentage limits, restrictions).
  - pipeline/CLAUDE.md previously listed HAS_COMPOSITION_RULE as "not emitted (Fix 6)"
    but code emits it — confirm this CLAUDE.md note is stale and edges are correctly emitted.
Known flags:
  - CLAUDE.md "Fix 6" note says not emitted; code does emit it. Stale doc — confirm and flag.
Conformity doc: docs/validation/conformity/E23-has-composition-rule.md
```

---

### E24 — REFERENCES  (various→various)

```
Status: PENDING
Report: —
Domain: Semantic cross-reference between any two rule/spell/weapon/core nodes. Emitted when
  page body contains a hyperlink to another wiki entry. §3–§9 (any cross-rule reference).
Source: body entry-links from SpecialRule, CoreRule, Spell, Weapon, MagicItem pages.
Producer: rule_parser.py · core_rule_parser.py · spell_parser.py · weapon_parser.py.
Authoritative: schema doc REFERENCES (7 endpoint-pair combinations) · constants EdgeType.REFERENCES.
Data: edges.json REFERENCES count=4715 · load_report REFERENCES=6031 (delta 1316).
Structural checks:
  - src and dst both resolve to existing node ids (across any node type).
  - Schema doc lists allowed endpoint pairs; verify no unexpected src/dst type combinations.
  - No self-loops (a page doesn't REFERENCE itself).
  - load_report delta +1316 is large — investigate what builder/seeds add for REFERENCES.
Domain checks:
  - Sample 10 REFERENCES edges: confirm referenced pair is semantically plausible
    (e.g. Fear rule → Terror rule; Killing Blow rule → Ward Save rule).
  - Spells that reference special rules they grant (e.g. a buff spell → Regeneration rule)
    should appear here.
Known flags:
  - load_report delta +1316: largest absolute delta of any edge type. Source unclear —
    may be post-load cross-link seeding. Investigate builder.py for REFERENCES derivation.
Conformity doc: docs/validation/conformity/E24-references.md
```

---

### E25 — HAS_INTRINSIC_RULE  (`:TroopType`→`:SpecialRule`)

```
Status: PENDING
Report: —
Domain: Rules that all units of a troop type inherently have (not purchased). §4 Troop Types.
  Examples: Chariots → Impact Hits; Monsters → Large Target; War Beasts → Skirmishers.
Source: troop-type pages (body entry-links to rule pages) + TROOP_TYPE_SEED constants.
Producer: rule_parser.py (HAS_INTRINSIC_RULE from body links when handling troop-type pages).
Authoritative: schema doc HAS_INTRINSIC_RULE · constants EdgeType.HAS_INTRINSIC_RULE.
Data: edges.json HAS_INTRINSIC_RULE count=80 · load_report HAS_INTRINSIC_RULE=80.
Structural checks:
  - src resolves to a TroopType id; dst resolves to a SpecialRule id.
  - 80 edges across 40 TroopType nodes = avg 2 intrinsic rules per type.
  - Verify dst SpecialRule ids exist in special_rules.json.
Domain checks:
  - Domain doc §4 table lists intrinsic rules per type:
    Heavy Infantry → Steady in the Ranks; Monstrous Infantry → Clumsy;
    Chariots → Impact Hits; Monsters → Large Target; War Beasts → often Skirmishers.
  - Spot-check 3 canonical troop types for expected intrinsic rule links.
  - All 13 canonical types should have ≥1 HAS_INTRINSIC_RULE edge where applicable.
Known flags: none specific; TROOP_TYPE_SEED in constants.py seeds numeric values but intrinsic
  rules come from body links — verify both sources are active.
Conformity doc: docs/validation/conformity/E25-has-intrinsic-rule.md
```

---

### E26 — CLARIFIES  (`:FAQ`→rule/spell/unit/etc.)

```
Status: PENDING
Report: —
Domain: An FAQ entry clarifies a rule, unit, weapon, or spell. Enables graph traversal
  from rule to relevant Q&A. §9–§12.
Source: FAQ page body entry-hyperlinks (direct, rare) + coordinator two-pass name-matching
  (primary source).
Producer: pipeline/scraper/parsers/faq_parser.py (direct links) +
  pipeline/scraper/parsers/__init__.py coordinator two-pass (name-match).
Authoritative: schema doc CLARIFIES · constants EdgeType.CLARIFIES.
Data: edges.json CLARIFIES count=474 · load_report CLARIFIES=510 (delta 36).
Structural checks:
  - src resolves to a FAQ id; dst resolves to any node id (SpecialRule, CoreRule, Unit, etc.).
  - 244 FAQs; 203 with CLARIFIES = 41 unlinked. Confirm count.
  - Verify dst node type distribution (should be mostly SpecialRule and CoreRule).
  - No FAQ should appear as both src and dst.
Domain checks:
  - Sample 5 CLARIFIES edges: confirm FAQ question is semantically related to the linked rule.
  - The 41 unlinked FAQs — spot-check 3 to determine if name-matching could link them
    or if they genuinely reference items not in the graph.
Known flags:
  - 41 FAQs without CLARIFIES edges — coordinator name-matching coverage gap.
  - load_report delta +36: builder/seeds add 36 more CLARIFIES post-load.
Conformity doc: docs/validation/conformity/E26-clarifies.md
```

---

### E27 — AMENDS  (`:Errata`→rule/spell/weapon/etc.)

```
Status: PENDING
Report: —
Domain: An errata entry amends (corrects) a rule, unit, weapon, or spell. §9–§12.
Source: Errata page body entry-hyperlinks (direct) + coordinator two-pass name-matching.
Producer: pipeline/scraper/parsers/errata_parser.py (direct) +
  pipeline/scraper/parsers/__init__.py coordinator two-pass.
Authoritative: schema doc AMENDS · constants EdgeType.AMENDS.
Data: edges.json AMENDS count=385 · load_report AMENDS=407 (delta 22).
Structural checks:
  - src resolves to an Errata id; dst resolves to any node id.
  - 210 errata; 185 with AMENDS = 25 unlinked.
  - Verify dst node type distribution.
Domain checks:
  - Sample 5 AMENDS edges: confirm errata corrected_text is plausibly linked to the dst rule.
  - The 25 unlinked errata — spot-check 3 to diagnose.
Known flags:
  - 25 errata without AMENDS edges — name-matching gap.
  - original_text always None — limits semantic usefulness of AMENDS edges (reader can't see
    what was corrected, only what it was corrected to).
  - load_report delta +22.
Conformity doc: docs/validation/conformity/E27-amends.md
```

---

### E28 — TERRAIN_INTERACTION  (`:SpecialRule`/`:TroopType`→`:Terrain`, property `effect`)  [GAP VALIDATION]

```
Status: PENDING
Report: —
Domain: How a special rule or troop type interacts with terrain. §10 Terrain interactions.
  effect vocabulary: ignores, ignores_cover, ignores_dangerous_test, ignores_disruption,
  can_deploy_in, move_through_freely, cannot_enter.
  Examples: Fly → ignores all terrain; Skirmishers in woods → ignores_disruption;
  Ethereal → ignores all terrain; Scouts → can_deploy_in woods.
Source: pipeline/graph/seeds.py (seeded post-load, not from parsers).
Producer: pipeline/graph/seeds.py (seed_terrain_interactions function).
Authoritative: schema doc TERRAIN_INTERACTION · constants EdgeType.TERRAIN_INTERACTION ·
  pipeline/CLAUDE.md Fix 5 ("enabled but unverified in live graph").
Data: edges.json TERRAIN_INTERACTION count=0 (not in parsed data) ·
  load_report: likely 0 or absent from edge_counts.
Structural checks:
  - Confirm TERRAIN_INTERACTION does NOT appear in edges.json (it is seeded post-load).
  - Check if load_report edge_counts includes TERRAIN_INTERACTION and what count is shown.
  - Inspect seeds.py seed_terrain_interactions() — list the (rule, terrain, effect) triples
    it would seed.
  - Determine if seed_terrain_interactions() was actually called during the last build
    (check builder.py main flow and load_report for evidence).
Domain checks:
  - Domain doc §10 lists key rule→terrain interactions. Verify the seed list covers:
    Fly → all terrain (ignores), Skirmishers → Woods (ignores_disruption),
    Ethereal → all terrain (ignores), Scouts → Woods/terrain (can_deploy_in),
    Strider → specific terrain (move_through_freely).
  - If seed list is incomplete, identify which interactions are missing.
Known flags:
  - pipeline/CLAUDE.md explicitly marks this "enabled but unverified" (Fix 5).
  - seeds.py contains the seed data but whether it ran is unclear from load_report.
  - This is expected to be a FAIL or PASS WITH GAPS — document the gap clearly.
Conformity doc: docs/validation/conformity/E28-terrain-interaction.md
```

---

### E29 — HAS_OPTIONAL_WEAPON  (`:Unit`→`:Weapon`)  [GAP VALIDATION]

```
Status: PENDING
Report: —
Domain: Optional weapons a unit can purchase (distinct from optional rules). §8 Equipment.
  Example: a unit that can replace its standard weapon with a great weapon optionally.
Source: intended from unit pages (options links to weapon entries) — NOT EMITTED.
  Currently: optional weapons are classified as HAS_OPTIONAL_RULE with dst=weapon slug.
Producer: NONE — EdgeType.HAS_OPTIONAL_WEAPON defined in constants.py but zero emitters.
Authoritative: constants EdgeType.HAS_OPTIONAL_WEAPON (defined, unused) ·
  schema doc does NOT list HAS_OPTIONAL_WEAPON.
Data: edges.json HAS_OPTIONAL_WEAPON count=0 · load_report: 0.
Structural checks:
  - Confirm HAS_OPTIONAL_WEAPON does NOT appear in edges.json.
  - Identify in HAS_OPTIONAL_RULE edges how many have dst = a Weapon id (not SpecialRule id).
    These are the misclassified optional weapons that should be HAS_OPTIONAL_WEAPON.
  - Count: of 1272 HAS_OPTIONAL_RULE edges, how many have dst resolving to weapons.json?
Domain checks:
  - Domain doc §8.1 describes weapon options. Units like heavy infantry often have weapon
    upgrade options (e.g. swap to great weapons).
  - UNLOCKS_WEAPON (824 edges) covers paid weapon upgrades. HAS_OPTIONAL_WEAPON would cover
    free/conditional optional equipment.
  - Assess domain impact: is the weapon/rule distinction important for RAG queries?
    (e.g. "what optional weapons does unit X have?" requires distinct classification).
Known flags:
  - This is a known gap: optional weapons collapsed into HAS_OPTIONAL_RULE.
  - HAS_OPTIONAL_WEAPON in constants but absent from schema doc — gap in both dimensions.
  - This is expected to be a FAIL — document the scope of the gap clearly.
Conformity doc: docs/validation/conformity/E29-has-optional-weapon.md
```

---

*End of tracker. Total items: 52. All pending.*
