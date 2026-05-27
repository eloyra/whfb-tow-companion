# Pipeline Fix Plan — 2026-05-08

Implementation plan for the gaps identified in `pipeline-audit-2026-05-08.md`
and corrected in `pipeline-audit-review-2026-05-08.md`. Read both before
starting.

A coding agent should be able to execute this plan without further
investigation. Each fix lists: goal, scope, exact files and line ranges,
the change to make, and verification steps.

---

## Status update — 2026-05-27

**What has shipped since this plan was written (2026-05-08):**

- **Fix 1 ✅ DONE.** 37 `:Terrain` nodes parsed and in the graph; terrain slugs removed from
  `core_rules.json`; `builder.py` / `validator.py` wired; `load_report.json` confirms `Terrain 37/37 delta 0`.
- **Beyond-plan work also shipped:** `CLARIFIES` (517 edges, 83% FAQ coverage) and `AMENDS`
  (441 edges, 88% errata coverage) — listed as *out of scope* in this plan — now exist.
  `HAS_INTRINSIC_RULE` (80 edges) present.

**What has NOT been started:** Fixes 3, 4, 6, 7.

**Fix 5** (terrain-interaction seed) is ✅ verified — 9 `TERRAIN_INTERACTION` edges written live.

---

## Order of execution

~~Group A item 1 — ✅ DONE (`:Terrain` parser pipeline — see Fix 1).~~

Remaining order:

1. **Verify Fix 5** (zero-code) — live Cypher confirms the seed wrote `TERRAIN_INTERACTION` edges
   now that Terrain nodes exist. Investigate slug mismatches if count is 0.
2. **Fix 2 and Fix 6 independently** — both are small edge-emitter changes; neither blocks the
   other. Can be done in parallel.
3. **Fixes 3 + 4 together, bundled with Fix 7's unit-option HTML extraction** — all three touch
   `_options.py`; doing them in one pass avoids reworking that file twice. See the updated Fix 7
   section for the unit-option HTML strategy that complements the budget fixes.
4. **Fix 7 remainder** — weapon/spell stat enrichment via rendered HTML tables (independent of
   `_options.py`; can be done separately).

After all fixes: `make parse && make build-graph`, run the validator, spot-check the
originally-failing queries from the audit's 50-query table.

---

## Fix 1 ✅ DONE — Add `:Terrain` parser pipeline

> **Status as of 2026-05-27:** Complete. `terrain_parser.py` registered; `terrains.json` contains
> 37 nodes; `/battlefield-terrain/` entries removed from `core_rules.json`; `builder.py` and
> `validator.py` wired; `load_report.json` shows `Terrain 37/37 delta 0`. Section preserved as
> implementation reference.

### Goal
Stop terrain pages being classified as `core_rule`. Emit them as `:Terrain`
nodes so `seed_terrain_interactions()` writes non-zero edges and queries
about woods, dangerous terrain, open ground, etc. become answerable.

### Files to modify

| File | Change |
|------|--------|
| `pipeline/constants.py` | Add `NodeType.TERRAIN`; extend `NODE_TYPE_TO_LABEL`; add `"Terrain"` to `EMBEDDABLE_LABELS`. |
| `pipeline/scraper/utils.py` | Add `/battlefield-terrain/{slug}` URL pattern to `_PAGE_TYPE_PATTERNS`. |
| `pipeline/scraper/parsers/terrain_parser.py` | **New file.** Implements `TerrainParser`. |
| `pipeline/scraper/parsers/__init__.py` | Register `TerrainParser` in `_PARSERS`; add `"terrain": "terrains.json"` to `_NODE_TYPE_TO_FILE`. |
| `pipeline/graph/seeds.py` | No change required — already wired. |
| `pipeline/graph/builder.py` | No change required — already invokes `seed_terrain_interactions(driver)` at line 97. |
| `pipeline/graph/ddl.py` | No change required — `terrain_id` constraint already exists at line 32. |

### 1.1 `pipeline/constants.py`

In the `NodeType` class (around line 145-161) add:
```python
TERRAIN = "terrain"
```

In `NODE_TYPE_TO_LABEL` (around line 274-291) add:
```python
NodeType.TERRAIN: "Terrain",
```

In `EMBEDDABLE_LABELS` (around line 296-309) add:
```python
"Terrain",
```

### 1.2 `pipeline/scraper/utils.py:168-184`

In the `_PAGE_TYPE_PATTERNS` list, **insert before** the catch-all
`(re.compile(r"^/[^/]+/[^/]+$"), "core_rule")` entry:
```python
(re.compile(r"^/battlefield-terrain/[^/]+$"), "terrain"),
```

### 1.3 New file: `pipeline/scraper/parsers/terrain_parser.py`

Model on `pipeline/scraper/parsers/rule_parser.py` (simplest applicable
template). The parser's responsibilities:

1. Call `self._extract_next_data(html)` to get `pageProps`.
2. Read `pp["entry"]["fields"]` for: `name`, `slug`, `body`, `bodyIndex`,
   `pageReference`, `association`.
3. Verify the page is actually a terrain page by checking
   `fields["ruleType"][0]["fields"]["slug"] == "battlefield-terrain"` (defensive
   check, in case URL classification ever drifts).
4. Build full body text via `self._body_text(fields)`.
5. Apply heuristics over the body text to populate the seven structured
   properties (see table below).
6. Emit one `:Terrain` node, no edges from this parser. Edges come from
   `seed_terrain_interactions()` and from `REFERENCES` extracted by the
   coordinator's text-match pass.

#### Heuristics for structured fields

Because Contentful does **not** carry these as discrete fields, derive them
from `body_text`. Suggested patterns (case-insensitive, search the full
body text):

| Property | Heuristic |
|----------|-----------|
| `terrain_class` | Match against the schema's enumeration: `linear-obstacle`, `open-ground`, `difficult-terrain`, `very-difficult-terrain`, `dangerous-terrain`, `impassable-terrain`. Look in the page's first heading or first paragraph. Default `None` if no match. |
| `blocks_movement` | `True` if body contains `\bimpassable\b`. |
| `requires_dangerous_test` | `True` if body matches `\b(dangerous terrain test|take a dangerous terrain test)\b`. |
| `disrupts_units` | `True` if body matches `\bdisrupted\b` or `\bcannot claim (a |any )?rank bonus\b`. |
| `grants_cover` | Match `\b(soft cover|hard cover)\b`; store as `"soft"` / `"hard"` / `None`. (Schema accepts string for cover type.) |
| `movement_penalty` | Match `\b(half(ed)?|halve|moves at half|treat as difficult)\b`; store the matched phrase as a short string, or `None`. |
| `special_feature_benefit` | Free-text catch-all. Store the body text or a meaningful excerpt for queries that need narrative context. |

These heuristics are deliberately conservative — false negatives are
preferable to false positives. The validator (`pipeline/graph/validator.py`)
will catch any large-scale parse failure on next build.

#### Node shape (must conform to schema v3.0)

```python
{
    "id": slug,                                 # e.g. "woods"
    "url": url,                                 # full URL
    "source_citation_book": "Rulebook",         # from fields["association"][0]["fields"]["name"]
    "source_citation_page": fields["pageReference"],
    "last_updated": self._date_only(fetched_at),
    "terrain_class": ...,                       # from heuristic
    "movement_penalty": ...,                    # from heuristic
    "blocks_movement": ...,                     # from heuristic
    "disrupts_units": ...,                      # from heuristic
    "requires_dangerous_test": ...,             # from heuristic
    "grants_cover": ...,                        # from heuristic
    "special_feature_benefit": ...,             # from heuristic
    "name": fields["name"],
    "text": body_text,
    "i18n": self._make_i18n(name=fields["name"], text=body_text),
}
```

Return `ParseResult(nodes=[node], edges=[])` with `node_type="terrain"` so
the coordinator routes it to `terrains.json`.

### 1.4 `pipeline/scraper/parsers/__init__.py`

In `_PARSERS` (around line 67-79) add:
```python
"terrain": TerrainParser(),
```

In `_NODE_TYPE_TO_FILE` (around line 85-102) add:
```python
"terrain": "terrains.json",
```

Add the import at the top of the file:
```python
from .terrain_parser import TerrainParser
```

### 1.5 Re-classification of already-scraped terrain pages

Existing crawl manifest entries for `/battlefield-terrain/*` are tagged
`page_type="core_rule"` and the corresponding parsed records sit in
`data/parsed/core_rules.json:5620+`. Two options:

**Option A (preferred): re-run scrape for these pages.**
```bash
make scrape  # full re-crawl, idempotent — politeness delay applies
```
Or, if the crawler supports targeted refresh, re-fetch only
`/battlefield-terrain/*` URLs.

**Option B: reclassify in place.** Patch the manifest writer or add a
fix-up script that re-tags existing `core_rule` entries whose URL matches
`/battlefield-terrain/`. Then re-run `make parse` only.

After re-parse, terrain entries should:
- Appear in `data/parsed/terrains.json` (new file).
- Disappear from `data/parsed/core_rules.json` for the affected slugs.

### 1.6 Verification

1. Run `make parse`. Confirm `data/parsed/terrains.json` exists with N
   entries (expect ~7-14 based on the schema's catalogue).
2. Confirm those slugs no longer appear in `data/parsed/core_rules.json`.
3. Run `make build-graph`. Confirm the validator output shows non-zero
   `Terrain` node count and non-zero `TERRAIN_INTERACTION` edge count
   (currently 0 / 0).
4. In Neo4j browser run:
   ```cypher
   MATCH (t:Terrain) RETURN count(t);
   MATCH ()-[r:TERRAIN_INTERACTION]->() RETURN count(r);
   ```
5. Spot-check audit query #20: `MATCH (t:Terrain {id:"open-ground"}) RETURN t.text`.
6. Re-run pipeline tests: `make test`.

---

## Fix 2 ✅ DONE — Emit `SPLIT_PROFILE_OF` edges in `UnitParser`

### Goal
Distinguish mount profiles from rider profiles for multi-profile units
(Demigryph Knights, Blood Knights on Nightmares, Mortis Engine).

### Files to modify

| File | Change |
|------|--------|
| `pipeline/constants.py` | Add `EdgeType.SPLIT_PROFILE_OF`. |
| `pipeline/scraper/parsers/unit_parser.py` | After emitting `HAS_PROFILE`, also emit `SPLIT_PROFILE_OF` for mount profiles. |

### 2.1 `pipeline/constants.py:234-267`

In the `EdgeType` class, add (e.g. near `HAS_PROFILE`):
```python
SPLIT_PROFILE_OF = "SPLIT_PROFILE_OF"
```

### 2.2 `pipeline/scraper/parsers/unit_parser.py:130-160`

After the existing `HAS_PROFILE` edge emission inside the profile loop,
classify each profile and emit `SPLIT_PROFILE_OF` if the profile is a mount
or sub-component.

**Mount detection heuristic** (validated against `blood-knights`,
`demigryph-knights`, `mortis-engine` in `data/parsed/profiles.json`):

```python
def _is_mount_profile(profile: dict) -> bool:
    """Mount/sub-profiles have movement but no toughness or wounds."""
    has_movement = profile.get("M") not in (None, "-", "")
    no_toughness = profile.get("T") in (None, "-", "")
    no_wounds = profile.get("W") in (None, "-", "")
    return has_movement and no_toughness and no_wounds
```

Inside the existing loop in `unit_parser.py:132-158`, after the
`HAS_PROFILE` edge is appended:

```python
if _is_mount_profile(profile):
    # Direction: mount_profile -> parent unit
    result.edges.append(
        self._make_edge(
            profile_id,
            slug,
            EdgeType.SPLIT_PROFILE_OF,
            {"profile_role": "mount"},
        )
    )
```

The direction (`mount_profile → unit`) matches the schema convention
*"split profile OF the parent unit"*. Confirm by reading
`docs/schema/knowledge_graph_schema.md` for the `SPLIT_PROFILE_OF` block
before committing — if the schema requires the opposite direction, swap
`profile_id` and `slug`.

### 2.3 Verification

1. Run `make parse`. In `data/parsed/edges.json`, search for
   `"SPLIT_PROFILE_OF"`. Expect at least one edge per multi-profile unit.
2. Spot-check Demigryph Knights:
   ```cypher
   MATCH (u:Unit {id:"demigryph-knights"})<-[:SPLIT_PROFILE_OF]-(p:Profile)
   RETURN p.name;
   ```
3. Spot-check audit query #48.

---

## Fix 3 ❌ NOT STARTED — Set `points_budget` on `command_champion` upgrades

### Goal
Capture champion magic-item allowances (e.g. "A Seneschal may take up to
25 points of magic items") so audit query #44 becomes answerable.

### Files to modify

| File | Change |
|------|--------|
| `pipeline/scraper/parsers/_options.py` | Inside the `command_champion` branch (line 265-284), call `_BUDGET_RE` and pass `points_budget` into `_make_upgrade_node`. |

### 3.1 `pipeline/scraper/parsers/_options.py:265-284`

Inside the `m_champ = _CHAMPION_RE.search(text)` branch, before the
`_make_upgrade_node` call, derive the budget:

```python
budget_match = _BUDGET_RE.search(text)
points_budget = int(budget_match.group(1)) if budget_match else None
```

Then add `points_budget=points_budget` to the `_make_upgrade_node` keyword
arguments.

**Note:** `_BUDGET_RE` is `r"up\s+to\s+(?:a\s+total\s+of\s+)?(\d+)\s+points"`
which matches *"up to 25 points of magic items"* and *"up to 50 pts"* (after
normalisation upstream — confirm). If it doesn't already match `pts`, also
broaden the regex once and re-test all upstream uses.

### 3.2 Optional: profile-scope filtering in `_derive_can_take_item`

If you want budgets to be *strictly* scoped to the champion profile rather
than granted to the whole Unit, also modify
`pipeline/graph/builder.py:125-175`:

In `query_items` (line 136), change the WHERE clause to consider
`up.applies_to_profile`:
```cypher
MATCH (u:Unit)-[:HAS_UPGRADE]->(up:Upgrade)
WHERE up.upgrade_type IN ['magic_item_budget','command_bsb','command_champion']
  AND up.points_budget IS NOT NULL
OPTIONAL MATCH (u)-[:HAS_PROFILE]->(p:Profile {id: up.applies_to_profile})
WITH u, up, COALESCE(p, u) AS holder
MATCH (mi:MagicItem)
WHERE ...                             -- existing item filters
MERGE (holder)-[r:CAN_TAKE_ITEM]->(mi)
SET r.budget = up.points_budget,
    r.via_upgrade = up.id;
```

This change is **optional** because for most queries grant-to-Unit is fine
and avoids breaking existing query patterns. Decide before changing.

### 3.3 Verification

1. Run `make parse && make build-graph`.
2. In Neo4j:
   ```cypher
   MATCH (up:Upgrade {upgrade_type:"command_champion"})
   WHERE up.points_budget IS NOT NULL
   RETURN up.id, up.points_budget LIMIT 20;
   ```
3. Spot-check audit query #44.

---

## Fix 4 ❌ NOT STARTED — Reorder `_options.py` dispatch so standard-bearer cost is not lost

### Goal
A line like *"Upgrade one model to a standard bearer (+6 pts) who may carry
a magic standard worth up to 50 pts"* currently classifies as
`magic_standard_budget` only — the `+6 pts` standard-bearer cost is dropped.
Fix: emit a `command_standard` upgrade with `points_cost=6` AND attach
`magic_standard_budget=50` as a property on that same upgrade node, OR emit
both nodes correctly linked.

### Files to modify

| File | Change |
|------|--------|
| `pipeline/scraper/parsers/_options.py` | Reorder `_classify_and_emit` so `_STANDARD_RE` is tested before `_BUDGET_RE`; inside the standard branch, also call `_MAGIC_STANDARD_BUDGET_RE` and attach the budget. |

### 4.1 `pipeline/scraper/parsers/_options.py:180-242`

Current order in `_classify_and_emit`:
1. `_BUDGET_RE` (line 180) — fires on the embedded "up to 50 pts" portion.
2. `_WIZARD_RE` (line 203).
3. `_STANDARD_RE` (line 225) — never reached for this case.

Change:
1. Move the `_STANDARD_RE` block (lines 225-242) **before** the `_BUDGET_RE`
   block (line 180). Likewise move `_MUSICIAN_RE` and `_CHAMPION_RE`
   blocks ahead of `_BUDGET_RE` if they suffer the same pattern.
   (Audit and code review do not show this for musician/champion, but it is
   safer to test command branches first.)
2. Inside the new earlier `_STANDARD_RE` branch, after `pts, cu = _cost_and_unit(text)`:
   ```python
   magic_standard_match = _BUDGET_RE.search(text)
   magic_standard_budget = int(magic_standard_match.group(1)) if (
       magic_standard_match and _MAGIC_STANDARD_BUDGET_RE.search(text)
   ) else None
   ```
   Then pass `magic_standard_budget=magic_standard_budget` to
   `_make_upgrade_node` and ensure that helper persists it as a property on
   the `command_standard` node.

   The `_MAGIC_STANDARD_BUDGET_RE` guard ensures we only attribute the
   budget to the standard bearer when the surrounding text actually
   mentions "standard" / "magic standard" — not when it's an unrelated
   "up to N points" phrase.

### 4.2 `_make_upgrade_node` signature

Inspect the current signature in `_options.py` (helper near top of file).
If `magic_standard_budget` isn't already a known kwarg, add it and persist
it on the resulting node dict.

### 4.3 Downstream: `_derive_can_take_item` Cypher

`pipeline/graph/builder.py:150` (`query_standards`) currently matches:
```cypher
WHERE up.upgrade_type = 'magic_standard_budget' AND up.points_budget IS NOT NULL
```
After Fix 4, magic standard budgets may now live on `command_standard` nodes
in the `magic_standard_budget` property. Update the query to also match:
```cypher
WHERE (up.upgrade_type = 'magic_standard_budget' AND up.points_budget IS NOT NULL)
   OR (up.upgrade_type = 'command_standard'      AND up.magic_standard_budget IS NOT NULL)
```
And use `COALESCE(up.points_budget, up.magic_standard_budget)` for `r.budget`.

### 4.4 Verification

1. Run `make parse && make build-graph`.
2. Find a known-affected unit (e.g. inspect raw `data/raw/unit/` files for
   units with combined "standard bearer ... magic standard" lines —
   confirmed examples should appear in Empire of Man / Bretonnian unit
   pages).
3. Verify the unit now has a `command_standard` upgrade with
   `points_cost=6` AND `magic_standard_budget=50`.
4. Spot-check audit query #45.
5. Confirm no regression in other unit upgrade counts via the validator's
   `_check_node_counts` and `_check_edge_counts` (5% drop limit).

---

## Fix 5 ✅ DONE — Verified `seed_terrain_interactions()` writes edges

> **Status as of 2026-05-27:** Fix 1 is done so the prerequisite is met. Seed source slugs
> (`fly`, `ethereal`, `skirmishers`, `scouts`, `move-through-cover`) all exist in
> `special_rules.json`; target slugs match the 37 Terrain node IDs. The `load_report.json` does
> not track seed-only edges, so a live Cypher check is required. Needs no code change.

### Goal
Confirm the existing seed produces 9+ `TERRAIN_INTERACTION` edges now that `:Terrain` nodes exist.

### Verification only — no code changes

```cypher
MATCH (s)-[r:TERRAIN_INTERACTION]->(t:Terrain) RETURN count(r);
```
Should return at least 9 (matches the seed entries in
`pipeline/graph/seeds.py:40-90`).

If it returns 0 after Fix 1, debug:
- Verify the seed's `from_id` / `to_id` slugs match the actual node IDs
  in the graph (slugs may differ — e.g. `dangerous-terrain` vs `dangerous`).
- Verify the seed function is invoked (`pipeline/graph/builder.py:97`).

---

## Fix 6 ❌ NOT STARTED — Emit `HAS_COMPOSITION_RULE` in `ArmyListParser`

### Goal
Link an Army to the CoreRule node representing its army-list composition
page, so users can navigate from army → composition rules without hopping
through composition_list nodes.

### Files to modify

| File | Change |
|------|--------|
| `pipeline/constants.py` | Add `EdgeType.HAS_COMPOSITION_RULE`. |
| `pipeline/scraper/parsers/army_list_parser.py` | After deriving the army_slug, emit one `HAS_COMPOSITION_RULE` edge from the army to the army-list page (treated as a CoreRule). |

### 6.1 `pipeline/constants.py:234-267`

```python
HAS_COMPOSITION_RULE = "HAS_COMPOSITION_RULE"
```

### 6.2 `pipeline/scraper/parsers/army_list_parser.py`

After computing the army_slug at `_army_slug_from_list_slug()` (around
line 298) and before returning, emit:

```python
result.edges.append(
    self._make_edge(
        army_slug,
        list_page_slug,           # the slug of the army-list page itself, e.g. "skaven-army-list"
        EdgeType.HAS_COMPOSITION_RULE,
    )
)
```

The destination node is the army-list page, currently parsed as a
`:CoreRule`. No new node creation required.

### 6.3 Verification

1. Run `make parse && make build-graph`.
2. ```cypher
   MATCH (a:Army)-[r:HAS_COMPOSITION_RULE]->(c:CoreRule) RETURN count(r);
   ```
   Expect ~19 (one per army).
3. Verify validator does not regress.

---

## Fix 7 ❌ NOT STARTED — Weapon / spell / unit-option enrichment via rendered HTML (the HTML pivot)

> **Updated 2026-05-27.** The original Option A/B framing is superseded. The HTML pivot
> (`docs/plans/scraper-html-pivot-explained.md`) is the correct approach and defines the scope
> precisely. Summary recorded here; full rationale in that document.

### Decision

Use a **hybrid parser**: keep `_extract_next_data` (Contentful JSON) for identity / structural
fields (slug, name, content-type, `REFERENCES` via entry-hyperlink); add `BeautifulSoup`
`soup.select(...)` calls over the server-rendered DOM for stat tables and option lists. No new
HTTP fetch, no headless browser — the same `.html` file already contains both `__NEXT_DATA__`
and the rendered page. BeautifulSoup is an existing dependency.

### What HTML wins (populate previously-`None` fields)

| Parser | HTML selector | Fields unlocked |
|--------|--------------|-----------------|
| `weapon_parser.py` | `table.profile-table--weapon` columns: Range / Strength / Armour Piercing / Special Rules | `range`, `strength`, `ap`, `special_rules` (where cells carry `<a href>` links) |
| `spell_parser.py` | Rows: `<td><b>Casting Value</b></td>`, `Range`, `Type` (typed `<a href="/magic/...">`) | `casting_value`, `casting_value_boosted`, `range`, `spell_type` |
| `_options.py` / unit pages | `div.unit-profile__details--option` → `<a href="/weapons-of-war/{slug}">` (or `/magic-items/`, `/special-rules/`) + `(+N points)` suffix | Removes the two-pass `UNLOCKS_RULE → UNLOCKS_WEAPON/UNLOCKS_ITEM` relabelling; gives typed target and cost directly |

### What stays unreliable even after the pivot

These cannot be extracted from any HTML table or structured cell; they remain prose-inferred:

- **Terrain booleans** (`blocks_movement`, `disrupts_units`, etc.) — already handled by the slug
  lookup tables and regex heuristics in `terrain_parser.py` (Fix 1, done). Not a pivot concern.
- **Weapon `special_rules` → slugs** when the cell is plain text (no `<a href>`) — still requires
  name-matching fallback.
- **`SPLIT_PROFILE_OF`** (Fix 2), **`HAS_COMPOSITION_RULE`** (Fix 6), **`composition_percentages`**,
  and other structural gaps — orthogonal; not fixed by HTML.
- ~~`CLARIFIES`/`AMENDS` edge reliability~~ — mitigated: 83–88% coverage via name-matching already
  ships in the live graph. No longer a residual concern.

### ISR-shell miss-guard

Some pages may be served as ISR shells without the rendered table (the parser already warns
`"ISR fallback or missing data"` for missing `__NEXT_DATA__`). The same miss-guard must wrap the
`soup.select(...)` path: if the table is absent, leave the fields as `None` and log a warning —
do not raise an exception.

### Implementation scope (when ready)

1. Inspect 5-10 raw weapon HTML files in `data/raw/` to confirm `profile-table--weapon` column
   header names match the selector.
2. Add `_extract_weapon_stat_table(html)` and `_extract_spell_stat_rows(html)` helpers to
   `pipeline/scraper/parsers/base_parser.py`.
3. Call from `weapon_parser.py` and `spell_parser.py` to overwrite the previously-`None` fields.
4. **Bundle with Fixes 3+4**: extend `_options.py` to also read typed `href` + `(+N points)`
   from `div.unit-profile__details--option` in the same rework pass as the champion-budget and
   standard-bearer dispatch fixes.
5. Add regression tests in `tests/test_parsers.py` using raw HTML fixtures from `data/raw/`.

---

## Cross-cutting verification (after all fixes)

1. `make parse` — confirm new `terrains.json` exists; existing files unaffected.
2. `make build-graph` — confirm validator's 10 integrity checks all pass
   under the 5% drop threshold.
3. In Neo4j:
   ```cypher
   // sanity counts
   MATCH (t:Terrain) RETURN count(t);
   MATCH ()-[r:TERRAIN_INTERACTION]->() RETURN count(r);
   MATCH ()-[r:SPLIT_PROFILE_OF]->() RETURN count(r);
   MATCH ()-[r:HAS_COMPOSITION_RULE]->() RETURN count(r);
   MATCH (up:Upgrade {upgrade_type:"command_champion"}) WHERE up.points_budget IS NOT NULL RETURN count(up);
   MATCH (up:Upgrade {upgrade_type:"command_standard"}) WHERE up.magic_standard_budget IS NOT NULL RETURN count(up);
   ```
4. Re-run pytest: `make test`. All existing tests must still pass.
5. Walk the audit's 50-query table and reclassify the previously-failing
   queries (#4, #18, #19, #20, #21, #22, #44, #45, #48). Expected new
   ratings:
   - #18-#22 → ✅ (terrain nodes now exist).
   - #4 → ✅ (terrain nodes resolve).
   - #44, #45 → ✅ (budgets captured).
   - #48 → ✅ (SPLIT_PROFILE_OF emitted).
   - Queries #9, #12, #15, #16 remain ⚠️ unless Fix 7 is taken.

---

## Test additions

Stub regression tests should be filled in for the new behaviour:

| Test file | Coverage |
|-----------|----------|
| `tests/test_parsers.py` | TerrainParser: all heuristics; mount detection in UnitParser. |
| `tests/test_options_parsing.py` | Standard-bearer + magic-standard-budget combined line; champion + magic-item budget combined line. |
| `tests/test_graph_build.py` | `seed_terrain_interactions()` writes ≥9 edges; `_derive_can_take_item` now scopes to profiles (if Option in Fix 3.2 chosen). |

Use existing test fixtures as templates. Where new fixtures are needed,
copy raw HTML samples from `data/raw/` into `tests/fixtures/`.

---

## Out of scope for this plan

- `CLARIFIES`/`AMENDS` coordinator logic — **shipped** (83–88% coverage live as of 2026-05-27).
  No further work needed here.
- `HAS_INTRINSIC_RULE` extraction — **shipped** (80 edges in `load_report.json`). Already dynamic
  in `rule_parser.py:131-135`.
- Full alliance seed expansion or full terrain interaction seed expansion — data-curation tasks,
  not code tasks.
- Backend RAG pipeline (`backend/rag/`) — separate work item.

---

## Files referenced (canonical paths)

- `D:\Projects\whfb-tow-companion\pipeline\constants.py`
- `D:\Projects\whfb-tow-companion\pipeline\scraper\utils.py`
- `D:\Projects\whfb-tow-companion\pipeline\scraper\parsers\__init__.py`
- `D:\Projects\whfb-tow-companion\pipeline\scraper\parsers\base_parser.py`
- `D:\Projects\whfb-tow-companion\pipeline\scraper\parsers\rule_parser.py`
- `D:\Projects\whfb-tow-companion\pipeline\scraper\parsers\unit_parser.py`
- `D:\Projects\whfb-tow-companion\pipeline\scraper\parsers\army_list_parser.py`
- `D:\Projects\whfb-tow-companion\pipeline\scraper\parsers\_options.py`
- `D:\Projects\whfb-tow-companion\pipeline\scraper\parsers\weapon_parser.py`
- `D:\Projects\whfb-tow-companion\pipeline\scraper\parsers\spell_parser.py`
- `D:\Projects\whfb-tow-companion\pipeline\graph\builder.py`
- `D:\Projects\whfb-tow-companion\pipeline\graph\seeds.py`
- `D:\Projects\whfb-tow-companion\pipeline\graph\ddl.py`
- `D:\Projects\whfb-tow-companion\pipeline\graph\validator.py`
- `D:\Projects\whfb-tow-companion\docs\schema\knowledge_graph_schema.md`
- `D:\Projects\whfb-tow-companion\docs\decisions\` (read all ADRs before making decisions)
