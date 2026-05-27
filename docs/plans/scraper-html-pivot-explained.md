# HTML Pivot — Plain-language explainer

Companion to `scraper-html-pivot-and-llm-evaluation.md`. Answers three questions about
*why* and *how* the pipeline should parse rendered HTML instead of Contentful richtext for
certain fields. Claims here were verified against the live parsers and the `data/raw/` corpus.

## 1. Is rendered HTML better and safer than the CMS fields? For which entities? Why?

Yes — but only for the entities whose game stats GW renders into display tables that Contentful
never modeled as structured fields.

**HTML wins — Weapons, Spells, Unit options:**

- **Weapons.** `<table class="profile-table--weapon">` exposes named columns
  `Range / Strength / Armour Piercing / Special Rules` with values
  (e.g. asrai-longbow → `32"`, `S`, `-`, `-`). The current parser cannot get these from
  Contentful, so it hardcodes `range=None, strength=None, ap=None, special_rules=[]`
  (`weapon_parser.py:136-144`). The HTML table is the *only* reliable source.
- **Spells.** Rendered rows like `<td><b>Casting Value</b></td><td>7+</td>`, plus `Range` and
  `Type`, where `Type` is a typed link `<a href="/magic/magic-missiles">`. Contentful exposes
  these only as prose `body_text`.
- **Unit options.** `<div class="unit-profile__details--option">` wraps each option, with
  `<a href="/weapons-of-war/{slug}">` (or `/magic-items/`, `/special-rules/`) giving the target
  AND its type directly, plus cost as a `(+N points)` suffix. This removes the need for the
  two-pass `UNLOCKS_RULE → UNLOCKS_WEAPON/UNLOCKS_ITEM` relabelling (`parsers/__init__.py:212-231`).

Why "safer": named column headers, semantic CSS classes, and real `href` targets are stable
across content edits. Regex over English prose is not — and it is what leaves the weapon/spell
stat fields stuck at `None` today.

**HTML adds nothing — keep the Contentful JSON path:**

- Identity / structural fields (slug, name, content-type, `association`, `REFERENCES` via
  entry-hyperlink) are already clean and deterministic in the JSON.
- Terrain and FAQ/Errata are prose in *both* sources.

## 2. How can we parse HTML directly if the scraped page returns `__NEXT_DATA__` JSON?

It is not either/or. Each saved `.html` file contains BOTH:

1. `<script id="__NEXT_DATA__" type="application/json">…</script>` — the Contentful entry the
   parsers read today via `_extract_next_data`.
2. The full server-rendered DOM — Next.js static generation bakes real `<table>`, `<div>`, and
   `<a href>` elements into the static file (the site needs no JS rendering).

So no new HTTP fetch and no headless browser are required. Feed the same html string into
`BeautifulSoup(html, "html.parser")` and use `soup.select(...)` alongside the existing
`_extract_next_data` call — a hybrid parser: JSON for identity/structure, CSS selectors for the
stat tables. BeautifulSoup is already a dependency.

One caveat: ISR shell pages. Parsers already warn `"ISR fallback or missing data"` when
`__NEXT_DATA__` is absent; the selector path needs the same miss-guard and a fallback so a page
served without the rendered table does not silently produce empty fields.

## 3. What knowledge stays unreliable even after the HTML pivot?

> **Update 2026-05-27:** Items 2 and the terrain-heuristic claim have since shipped.
> See notes inline below.

Four things the pivot does NOT fix:

1. **Terrain booleans** — `blocks_movement`, `disrupts_units`, `requires_dangerous_test`,
   `grants_cover`, `movement_penalty`. The HTML is pure prose; these are reader-inferred from
   rules text. They come from slug-lookup tables + regex heuristics (`terrain_parser.py:50-103`).
   No structured cell exists to select.
   *(Note 2026-05-27: `terrain_parser.py` with these heuristics has shipped — Fix 1 done.
   37 `:Terrain` nodes are in the graph. This is no longer a pending gap.)*
2. **CLARIFIES / AMENDS edges** — FAQ→rule and Errata→rule. The bodies are prose with no
   resolved hyperlinks in *either* the Contentful JSON or the rendered HTML. Derived by
   case-insensitive name-matching with `_MIN_MATCH_LEN=5` (`parsers/__init__.py:351-438`).
   HTML provides no links to extract.
   *(Note 2026-05-27: the name-matching approach now achieves 83% CLARIFIES / 88% AMENDS
   coverage — 517 and 441 edges respectively. No longer a significant residual concern.)*
3. **Weapon `special_rules` → rule slugs** — only unreliable when the table cell holds plain
   text rather than an `<a href>` link (asrai-longbow's cell was just `-`). Where there is no
   link, mapping rule names to slugs still requires text guessing.
4. **`SPLIT_PROFILE_OF`, army `composition_percentages`, Upgrade nodes** — not present in any
   table either; these are orthogonal gaps.

Why: these are semantic/relational facts that live only as natural language or human inference —
never marked up as a field or a named cell. A CSS selector cannot extract what was never tagged.
This residual set is exactly the scope of Lane B (bounded LLM enrichment) in the parent plan.
