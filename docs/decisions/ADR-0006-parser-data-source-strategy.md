# ADR-0006 — Parser Data-Source Strategy

| Field       | Value                                               |
|-------------|-----------------------------------------------------|
| **Status**  | Accepted                                            |
| **Date**    | 2026-05-28                                          |
| **Deciders**| Project author                                      |
| **Tags**    | parsing, html, contentful, spells, weapons          |

---

## Context

The wiki at `tow.whfb.app` is a Next.js static site. Each saved HTML file contains two
independent data sources:

1. `<script id="__NEXT_DATA__">` — the Contentful CMS entry, which the parsers consumed
   from the start via `_extract_next_data`. Reliable for identity, structural relationships,
   and rich-text `REFERENCES` (Contentful entry-hyperlinks in body fields).
2. The server-rendered DOM — Next.js bakes `<table>`, `<div>`, and `<a href>` elements into
   the static HTML at build time. No JS rendering required.

After audit (2026-05-08), several fields critical to game queries were stuck at `None`
because Contentful never modeled them as discrete fields — they appear only in rendered stat
tables:

- Weapon stats: `range`, `strength`, `ap`, `special_rules`
  (from `<table class="profile-table--weapon">`)
- Spell metadata: `casting_value`, `range`, `spell_type`
  (from rendered stat rows and typed `<a href="/magic/...">`)

A secondary problem: every dedicated `/spell/{slug}` page was being misrouted to
`CoreRuleParser` (matching the generic `/{section}/{slug}` URL pattern), creating a
duplicate-id collision between a thin `Spell` node (emitted by the lore parser from embedded
references) and a mechanics-rich `CoreRule` node (emitted from the dedicated page).
`REFERENCES` edges originated from the `CoreRule` node, not the `Spell`.

---

## Decision

### 1 — Hybrid parsing: Contentful JSON + BeautifulSoup DOM

For fields where Contentful structured data exists, keep `_extract_next_data`. For stat
tables and unit-option lists, add `BeautifulSoup(html, "html.parser")` calls over the
**same `.html` file** — no new HTTP fetch, no headless browser. `beautifulsoup4` is an
existing dependency.

| Parser | HTML selector | Fields populated |
|---|---|---|
| `weapon_parser.py` | `table.profile-table--weapon` | `range`, `strength`, `ap`, `special_rules` (href-linked cells) |
| `spell_parser.py` | Stat rows + `<a href="/magic/...">` | `casting_value`, `range`, `spell_type` |

**Binding constraint — ISR-shell miss-guard:** Some pages may be served as ISR shells
without the rendered table. The same miss-guard that logs `"ISR fallback or missing data"`
when `__NEXT_DATA__` is absent must wrap every `soup.select(...)` call: if the selector
returns no rows, leave the fields as `None` and log a warning — never raise.

### 2 — Spell source-of-truth: dedicated `/spell/{slug}` pages via `SpellParser`

- `pipeline/scraper/parsers/spell_parser.py` — rewritten to parse a single `/spell/{slug}`
  dedicated page; emits one `Spell` node with all structured fields plus `REFERENCES` edges
  from body hyperlinks.
- `pipeline/scraper/parsers/lore_parser.py` — new file extracted from the old
  `spell_parser.py`; emits one `Lore` node plus `BELONGS_TO_LORE` edges from embedded spell
  slugs. Emits no `Spell` nodes.
- URL routing override in `parsers/__init__.py` redirects manifest entries whose URL starts
  with `/spell/` to `SpellParser`, not `CoreRuleParser`.

This resolved the duplicate `Spell`/`CoreRule` node collision. 139 spells now have
`spell_type` and `casting_value` populated; 0 duplicate `CoreRule` nodes remain from
`/spell/` URLs.

---

## Alternatives rejected

### `llm-scraper`

TypeScript + Playwright. Wrong language for a Python/uv monorepo, wrong tool for a static
`__NEXT_DATA__` site. Categorisation is already deterministic (URL regex + 14-parser
registry). Categorisation was never the bottleneck.

### `ScrapeGraphAI` as a scraper replacement

Recurring LLM cost on every `make scrape`, breaks pipeline determinism. Its
`SmartScraperGraph` is "fetch URL → LLM → JSON" — the HTML is already fetched, and the
structured parts are better served by CSS selectors at zero marginal cost.

### Regex over `body_text` / `bodyIndex`

The Contentful JSON `bodyIndex` field is a flattened prose summary, not the stat table.
Regex over it produces false negatives on most weapons. This is exactly what left the
fields `None` before the pivot.

---

## Consequences

### Positive

- Weapon `range`, `strength`, `ap` populated (226 weapons with `range IS NOT NULL` in
  live graph).
- All 139 spells have `spell_type` and `casting_value` populated.
- `REFERENCES` edges now flow from `Spell` nodes, enabling correct multi-hop rules traversal
  (e.g. Regeneration → Unquiet Spirits path now resolves through the `Spell` node).
- No new dependencies, no new fetches.

### Negative / accepted trade-offs

- Two parsers per lore/spell domain (`LoreParser` + `SpellParser`) — routing logic in
  `parsers/__init__.py` must be kept in sync.
- Fields with no HTML table or typed link remain `None` and are open gaps: `armour_value`,
  war-machine stats (`shots`, `template_type`, `bounce`, `is_indirect`),
  `casting_value_boosted`. See `pipeline/CLAUDE.md` Known gaps.
- Weapon `special_rules` → slugs populated only when the table cell carries an `<a href>`
  link; plain-text cells still require a name-match fallback.

---

## References

- Full rationale + tool evaluation: `docs/plans/scraper-html-pivot-and-llm-evaluation.md`
- Plain-language explainer + residual catalogue: `docs/plans/scraper-html-pivot-explained.md`
- Parse output contract: ADR-0004
- Graph storage conventions: ADR-0005
