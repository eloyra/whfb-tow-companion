# Audit Review — `pipeline-audit-2026-05-08.md`

A second-pass validation of every claim in the audit dated 2026-05-08, checked
against the current state of the repository. Each entry records the audit's
claim, the verdict (Confirmed / Refuted / Partial), and verbatim file:line
evidence so a coding agent can act on this report without re-investigation.

---

## Summary

- **20 claims confirmed** as written.
- **2 claims refuted**: `CLARIFIES`/`AMENDS` already cover non-rule targets;
  `HAS_INTRINSIC_RULE` is dynamically emitted, not seed-only.
- **2 claims partial / mis-framed**: weapon stat enrichment cannot be done
  via regex over Contentful `bodyIndex` (data is in raw HTML tables, not the
  Contentful JSON the parser reads); standard-bearer/budget short-circuit bug
  is real but in the opposite direction described (the budget regex wins, so
  the standard-bearer cost is lost — not the budget).

The audit's overall picture (terrain missing, profile/composition edges
missing, weapon/spell structured fields missing, two budget-classifier bugs)
is correct. The proposed fix list needs three corrections before execution
(see Section 4).

---

## 1. Section-by-section verification

### GAP 1 — `:Terrain` Nodes Not Parsed — **CONFIRMED**

| Sub-claim | Verdict | Evidence |
|-----------|---------|----------|
| `NodeType` enum has no `TERRAIN` member | Confirmed | `pipeline/constants.py:145-161` lists 16 members; no `TERRAIN`. |
| `NODE_TYPE_TO_LABEL` has no `"terrain"` key | Confirmed | `pipeline/constants.py:274-291` mirrors the enum; no terrain entry. |
| No `TerrainParser` class | Confirmed | Glob `pipeline/scraper/parsers/terrain*` empty; codebase grep for `class.*Terrain` returns only DDL index lines. |
| `classify_url()` has no `/battlefield-terrain/` pattern | Confirmed | `pipeline/scraper/utils.py:168-184` — pattern absent. Catch-all `^/[^/]+/[^/]+$` at line 183 routes terrain pages to `core_rule`. |
| Terrain pages misclassified as core rules | Confirmed | `data/parsed/core_rules.json:5620+` contains entries for `woods`, `dangerous-terrain`, etc. |
| `seed_terrain_interactions()` writes 0 edges | Confirmed | `pipeline/graph/seeds.py:5` docstring admits "writes zero edges"; `pipeline/graph/seeds.py:122` Cypher `MATCH (t:Terrain {id: $to_id})` matches nothing because no `:Terrain` nodes exist. Function is invoked unconditionally at `pipeline/graph/builder.py:97`. |
| `terrain_id` constraint exists in DDL | Confirmed | `pipeline/graph/ddl.py:32` defines the uniqueness constraint; `ddl.py:54` adds an index on `terrain_class`. Both are dead code today. |
| Schema defines `:Terrain` with the seven named properties | Confirmed | `docs/schema/knowledge_graph_schema.md:330-386` defines `terrain_class`, `movement_penalty`, `blocks_movement`, `disrupts_units`, `requires_dangerous_test`, `grants_cover`, `special_feature_benefit`, plus `name`, `text`, `i18n`. |

**Five queries blocked by this gap, all from the audit's 50-query analysis:**
queries #18, #19, #20, #21, #22 (plus partial query #4).

---

### GAP 2 — `SPLIT_PROFILE_OF` Edges Not Emitted — **CONFIRMED**

- `pipeline/scraper/parsers/unit_parser.py:156-158` emits only `HAS_PROFILE`
  edges, with `{"order": order}` as the only edge property.
- Codebase-wide grep for `SPLIT_PROFILE_OF` / `split_profile` returns zero
  hits in `pipeline/` source — only mentions in `docs/schema/`,
  `pipeline/CLAUDE.md:102`, and the audit itself.
- `EdgeType` enum at `pipeline/constants.py:234-267` does not declare
  `SPLIT_PROFILE_OF`.

**Caveat the coding agent must resolve before implementation:** the audit
suggests detecting mounts by name or by absence of weapons/rules. Examination
of raw `data/raw/unit/blood-knights.html` confirms there is **no** mount
flag, no contentType reference, and no link to a separate mount unit in the
profile dict. Mounts are inlined as raw stat blocks. A reliable heuristic
observed across `blood-knights`, `demigryph-knights`, `mortis-engine` is:
a profile is a mount/sub-component when `M is not None` AND `T is None` AND
`W is None` (mount has movement but no toughness or wounds).

---

### GAP 3 — Weapon Structured Profile Fields All `None` — **PARTIAL**

- **Confirmed:** `pipeline/scraper/parsers/weapon_parser.py:134-144`
  explicitly sets `range`, `strength`, `ap`, `special_rules` (=`[]`),
  `armour_value`, `shots`, `template_type`, `is_indirect`, `bounce` to
  `None`. Comment block reads:
  > Structured profile fields — not present in Contentful data model;
  > values are only in the body text and require a separate enrichment pass.

- **Refuted (recovery path):** the audit recommends a regex pass over
  `bodyIndex` / `description`. Investigation of multiple raw weapon pages
  (`data/raw/weapon/handgun.html`, `cathayan-lance.html`, `cavalry-spear.html`,
  30+ confirmed via grep) shows the structured stats live in raw HTML
  `<table>` cells, not in the Contentful `__NEXT_DATA__` JSON the parser
  reads. The `bodyIndex` field in Contentful is a flattened summary, not
  the stat table.

  A regex over `bodyIndex` will return false negatives on most weapons.
  The enrichment pass must either:
  1. Re-open the raw HTML and parse the `<table>` rows, OR
  2. Be abandoned in favour of vector-search-only answers for these fields.

  **Decision required before scoping work.**

---

### GAP 4 — Spell Structured Fields Mostly `None` — **CONFIRMED**

- `pipeline/scraper/parsers/spell_parser.py:157-161` (standard lores) and
  `:227-231` (renegade lores) set `spell_type`, `duration`, `target`,
  `casting_value_boosted` to `None`.
- `casting_value`, `range`, `casting_value_override` ARE extracted at lines
  138-141 (standard) and 212-228 (renegade table parsing).
- The same Contentful caveat from GAP 3 may apply — the coding agent should
  inspect raw spell HTML before committing to a regex-over-`bodyIndex`
  enrichment.

---

### GAP 5 — `HAS_COMPOSITION_RULE` Edge Not Emitted — **CONFIRMED**

- Codebase-wide grep for `HAS_COMPOSITION_RULE` returns zero hits in
  `pipeline/` source.
- Not declared in `EdgeType` (`pipeline/constants.py:234-267`).
- `pipeline/scraper/parsers/army_list_parser.py` emits `HAS_LIST`,
  `HAS_SLOT`, `SLOT_ALLOWS`, `ALLIED_WITH`, `HAS_UPGRADE` — but not
  `HAS_COMPOSITION_RULE`.

---

### GAP 6 — Champion Magic Item Budget Not Captured — **CONFIRMED**

- `pipeline/scraper/parsers/_options.py:265-284` (the `command_champion`
  branch in `_classify_and_emit`) only calls `_cost_and_unit(text)`. There
  is no `_BUDGET_RE` call and `points_budget` is never set on champion
  upgrades.
- `pipeline/graph/builder.py:125-175` (`_derive_can_take_item`) — none of
  the three Cypher passes references `up.applies_to_profile`. Even if a
  separate `magic_item_budget` upgrade carries `applies_to_profile`, it is
  granted to the Unit, not scoped to the Profile.

---

### GAP 7 — Standard Bearer Budget Detection — **CONFIRMED, direction reversed**

- The audit claims `_STANDARD_RE` matches first and the budget is lost.
- **Reality:** `_options.py:180` checks `_BUDGET_RE` *before* `_STANDARD_RE`
  (line 225). On a line like
  *"Upgrade one model to a standard bearer (+6 pts) who may carry a magic
  standard worth up to 50 pts"*, the budget branch wins and the
  `command_standard` upgrade is never emitted — so the **standard bearer's
  `+6 pts` cost is lost**, not the budget.
- Same code area, same fix surface, but the bug symptom is reversed. The
  fix order matters: the agent must restructure the dispatch, not just add
  a follow-up regex call.

---

### GAP 8 — Edge Inventory — partially refuted

| Edge | Audit claim | Verdict | Evidence |
|------|-------------|---------|----------|
| `TERRAIN_INTERACTION` | seed only, 0 edges | Confirmed | `pipeline/graph/seeds.py:40-135`. |
| `SPLIT_PROFILE_OF` | missing | Confirmed | See GAP 2. |
| `HAS_COMPOSITION_RULE` | missing | Confirmed | See GAP 5. |
| `CLARIFIES → Unit/Spell/Weapon/Terrain/MagicItem` | partial | **Refuted** | `pipeline/scraper/parsers/__init__.py:333-341` — `_CLARIFIABLE_TYPES` already contains `special_rule`, `core_rule`, `unit`, `spell`, `weapon`, `magic_item`. Direct entry hyperlinks emitted by `faq_parser.py:99` cover whatever the FAQ body links to. The remaining gap is in source data (FAQ bodies often lack resolved hyperlinks), not coordinator coverage. |
| `AMENDS → Unit/MagicItem/Terrain` | partial | **Refuted** | Same `_CLARIFIABLE_TYPES` set referenced by `__init__.py:401-415`; `errata_parser.py:91` emits AMENDS to any linked entry. |
| `HAS_OPTIONAL_RULE` | present | Confirmed | `unit_parser.py:197, 203`. |
| `HAS_INTRINSIC_RULE` | seed only | **Refuted** | `pipeline/scraper/parsers/rule_parser.py:131-135` dynamically emits this edge whenever a rule's `affects` link points to a troop type. `data/parsed/edges.json:2807-3281+` already contains 100+ such edges. There is no seed for `HAS_INTRINSIC_RULE`. |

---

## 2. Sections 3 & 4 — Numerical claims

| Audit claim | Verdict | Evidence |
|-------------|---------|----------|
| "70% answerable / 20% partial / 10% blocked" | Numerically derived from the audit's own 50-query table; not separately verified, but each individual query's rating depends on gaps 1-7 above and matches the verified state. |
| "10 integrity checks, 5% drop limit" | Confirmed | `pipeline/graph/validator.py:26` (`_DROP_THRESHOLD = 0.05`); `validator.py:58-67` lists 10 named checks. |
| Two-pass coordinator (`UNLOCKS_RULE` → `UNLOCKS_WEAPON/ITEM`, `rule_add` → `weapon_add`) | Confirmed | `pipeline/scraper/parsers/__init__.py:209-246`. Lives in coordinator, **not** the builder. The audit's Section 4 lists `weapon_add` as a `_options.py` output, but the actual emission is by this post-pass — minor wording correction. |
| `_derive_can_take_item` runs unconditionally (three passes) | Confirmed | `pipeline/graph/builder.py:93` (call site), `:125-175` (passes). |
| Idempotent MERGE-based writes | Confirmed | All builder writes use MERGE. |

---

## 3. Notes on the test inventory

The audit's Section 4 test table is mostly accurate but worth flagging:
several stub files (`test_parsers.py`, `test_retriever.py`, `test_pipeline.py`,
`evaluate.py`) remain stubs. The next implementation wave should fill at
least `test_parsers.py` with regression tests for the new TerrainParser,
the standard-bearer/budget fix, and the champion budget fix.

---

## 4. Required corrections to the audit's fix recipes

### 4.1 GAP 3 weapon enrichment

The audit says: *"A regex-based enrichment pass on the `bodyIndex` or
`description` text of weapon pages."*

**This will not work.** The Contentful JSON does not contain the structured
stat strings. Re-scope to one of:
- HTML-table extraction in `weapon_parser.py` (read raw HTML alongside
  `__NEXT_DATA__`), or
- Defer structured field extraction; rely on vector retrieval over the
  weapon prose.

Pick before scoping the fix.

### 4.2 GAP 7 dispatch reorder

The audit says: *"After `_STANDARD_RE` match, run `_MAGIC_STANDARD_BUDGET_RE`
and `_BUDGET_RE` on the same text."*

**This is the wrong direction.** `_BUDGET_RE` already runs first and wins.
Fix: in `_options.py:180-200` (`_classify_and_emit`), test
`_STANDARD_RE` *before* `_BUDGET_RE`, then call `_MAGIC_STANDARD_BUDGET_RE`
inside the standard-bearer branch to attach the budget as a property on the
`command_standard` upgrade node.

### 4.3 Drop two longer-term items

- Audit Section 5 item 8 (*"`CLARIFIES`/`AMENDS` extended targets"*): already
  done. If coverage is poor, the source data is the problem.
- Audit Section 5 item 10 (*"`HAS_INTRINSIC_RULE` dynamic extraction"*):
  already done in `rule_parser.py:131-135`. If coverage is poor, the
  problem is which `affects` links exist in the source data.

---

## 5. Confidence statement

This validation was performed by reading current source files at
`D:\Projects\whfb-tow-companion`. All file:line references reflect the
state of the repository at the time of writing (2026-05-08). The
implementation plan in `pipeline-fix-plan-2026-05-08.md` builds on these
findings.
