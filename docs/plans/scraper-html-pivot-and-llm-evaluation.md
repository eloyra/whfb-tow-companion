# Plan: Evaluate llm-scraper / ScrapeGraphAI vs HTML parsing for the WHFB ToW pipeline

## Context

You asked whether `llm-scraper` or `ScrapeGraphAI` would simplify scraping, category assignment, and relationship extraction. Investigation showed two things:

1. Page-to-category routing is already solved deterministically (URL regex in `pipeline/scraper/utils.py` → 14-parser registry in `pipeline/scraper/parsers/__init__.py`), and structural edges + `REFERENCES` come from CMS-linked fields. **Categorization is not the bottleneck.**
2. The actual fragility is regex over prose that the Contentful JSON only exposes as `body_text` strings. Concentrated in `pipeline/scraper/parsers/_options.py` (602 LOC, 10 regex families), `army_list_parser.py` (329 LOC), `terrain_parser.py` (212 LOC, 5 boolean regexes), and `weapon_parser.py` (`_CLASS_HINTS` keywords). Documented gaps in `pipeline/CLAUDE.md` (Known gaps) and `docs/decisions/ADR-0006-parser-data-source-strategy.md`: weapon stats (range/strength/AP/special_rules/armour_value/shots/template/indirect/bounce) all `None`; spell metadata (spell_type/duration/target/casting_value_boosted) all `None`; `SPLIT_PROFILE_OF` absent; `CLARIFIES`/`AMENDS` derived by `_MIN_MATCH_LEN=5` name-match.

Your follow-up — *"would parsing real HTML be simpler?"* — is the right question. Inspection of `data/raw/`:

- **Weapons** (`data/raw/weapon/asrai-longbow.html`): clean `<table class="profile-table--weapon">` with named column headers `Range / Strength / Armour Piercing / Special Rules`. CSS selectors here would be reliable enough to solve **all** the GAP 3 fields with zero LLM and zero regex.
- **Spells** (`data/raw/spell/battle-magic.html`): clean `<td><b>Casting Value</b></td><td><p>7+</p></td>` rows, same pattern for `Range`, embedded `<table class="profile-table--spell">` per spell. Solves GAP 4 fields with CSS selectors.
- **Unit options** (`data/raw/unit/arachnarok-spider.html`): the rendered HTML wraps options in `<div class="unit-profile__details--option"><ul><li><p>May take a <a href="/weapons-of-war/{slug}">…</a> (+35 points)</p></li></ul></div>`. Semantic wrapper classes, real `<a href>` links to target slugs, and cost in a predictable `(+N points)` suffix. Significantly cleaner than walking Contentful richtext by `nodeType`.
- **Terrain** (`data/raw/terrain/arboreal-gloom.html`): pure prose paragraphs. No structured fields in HTML; the booleans are reader-derived. HTML offers nothing here.
- **FAQ / Errata**: answer text is prose. HTML offers nothing for `CLARIFIES`/`AMENDS` either.

This reshapes the question. The dominant win is not LLM scraping — it is **switching from Contentful-JSON richtext walking to rendered-HTML parsing** for the fields where Contentful never modeled them as structured data. LLM enrichment shrinks to a narrow residual: terrain booleans, and reranking the FAQ/errata name-match candidate set.

## Verdict on the candidate tools

**Reject `llm-scraper`.** TypeScript + Playwright. Wrong language for this Python/uv monorepo, wrong tool for a static `__NEXT_DATA__` site, duplicates what `langchain-openai` + Pydantic already do natively.

**Reject `ScrapeGraphAI` as a scraper replacement.** Recurring LLM cost on every `make scrape`, breaks determinism of `make pipeline`, and provides no gain over `requests` + `bs4` on a static site. Its `SmartScraperGraph` is "fetch URL → LLM → JSON" — for our case the HTML is already fetched, and the parts we need are now known to be either structured HTML (tables, semantic divs) or genuinely free prose. The structured cases don't need an LLM; the prose cases are better served by a focused LangChain `with_structured_output()` call than by the graph machinery.

**Keep `ScrapeGraphAI` as a possible candidate only after the HTML pivot, only for the residual prose fields, and only if it beats a plain LangChain baseline on the same evaluation set.** Same conditional adoption as before, but with a much smaller addressable scope.

## Recommended approach (two lanes, sequenced)

### Lane A — HTML parsing pivot (primary fix, no LLM)

Move the extraction of fields that exist as structured HTML from Contentful richtext walking to direct HTML parsing with BeautifulSoup CSS selectors. Keep the Contentful JSON path for everything it does well: slugs, names, content-type classification, CMS-modeled fields, `REFERENCES` via `entry-hyperlink`, structural edges via CMS associations.

Hybrid pattern, applied per parser:
- Continue calling `_get_next_data(html)` for the structural/identity fields.
- Also keep a `BeautifulSoup(html, "html.parser")` view; for each target field, prefer `soup.select("table.profile-table--weapon …")` over regex-over-`body_text`.
- Fall back to the existing logic if the selector misses (so we never regress on pages that lack the table).

Concrete targets and selectors observed in `data/raw/`:

1. **Weapons** — `pipeline/scraper/parsers/weapon_parser.py`
   - Selector: `table.profile-table--weapon thead th` for column headers, `tbody td` for values.
   - Fields recovered: `range`, `strength`, `armour_piercing`, `special_rules`.
   - Eliminates GAP 3 without LLM.

2. **Spells** — `pipeline/scraper/parsers/spell_parser.py`
   - Selector: within each `div.spell`, find the embedded `table` of `<td><b>Label</b></td><td>value</td>` rows; map labels to fields (`Casting Value`, `Range`, `Type`, `Duration`, `Target`).
   - Eliminates GAP 4 without LLM.
   - Also lets the parser drop one of its two extraction strategies (the "renegade" richtext heading/table walker), shrinking ~80 LOC.

3. **Unit options** — `pipeline/scraper/parsers/_options.py`
   - Selector: `div.unit-profile__details--option > ul > li` for each option line; `a[href^="/weapons-of-war/"]`, `a[href^="/magic-items/"]`, `a[href^="/special-rules/"]` give typed targets directly without `UNLOCKS_RULE → UNLOCKS_WEAPON/ITEM` relabeling.
   - Cost extracted from `(+N points)` suffix on `<li>` text content.
   - Champion/musician/standard markers in adjacent `unit-profile__details--*` div classes if present.
   - Expected reduction: large fraction of the 10 regex families in `_options.py`. Conservatively half by LOC; functionally cleaner because edge types come from URL paths, not text inference.
   - **Important:** this file drives army-construction validity. Implement as a feature-flagged side-by-side path: emit both regex-derived and HTML-derived edges into separate JSON files, diff them across the entire `data/raw/unit/` corpus before swapping the default.

4. **Army lists** — `pipeline/scraper/parsers/army_list_parser.py`
   - Need a quick inspection of a representative page to confirm whether "0-N per Y points" lives in structured HTML or in prose. If structured, fold into Lane A; if prose, leave alone or move to Lane B.

5. **Cross-page hyperlinks** — anywhere that `entry-hyperlink` in Contentful currently produces `REFERENCES`, the rendered HTML carries the same information as `<a class="detailed-link" href="/..." >`. The CMS path is already deterministic; no change unless we find pages with rendered links missing from the CMS body.

Determinism: HTML parsing stays deterministic and free. `make pipeline` reproducibility unchanged. No new dependencies — BeautifulSoup is already in use.

### Lane B — LLM enrichment for genuinely prose-only fields

After Lane A, the residual scope is small enough to be worth a bounded experiment:

- **Terrain booleans** in `pipeline/scraper/parsers/terrain_parser.py` (5 fields × ~25 pages) — best first target. Built-in ground truth from the existing `_TERRAIN_CLASS_BY_SLUG` / `_BLOCKS_MOVEMENT_BY_SLUG` lookup tables.
- **`CLARIFIES` / `AMENDS` precision filter** over the candidate set produced by `_derive_clarifies_amends` in `pipeline/scraper/parsers/__init__.py:351-438`. LLM as a re-ranker, never as an open-ended generator — bounds cost to existing recall set.
- **Weapon `special_rules` text → linked rule slugs** if Lane A leaves that field as free text rather than typed `<a href>` links. Only if needed after HTML inspection.

For all of these, implement as a **post-parse sidecar stage** with:
- Pydantic schema as the single source of truth.
- `temperature=0`, `seed=42`, content-hash cache key `sha256(body_text + schema_version + model_id + prompt_version)`.
- Mandatory `ENRICHMENT_BUDGET_USD` env-var pre-flight (default $1.00) using `tiktoken` token estimate.
- Skip-silently fallback when `OPENAI_API_KEY` missing → graph build continues from the regex-derived files.
- LangChain + Pydantic as the baseline. Benchmark `ScrapeGraphAI` against it only after the baseline meets the accuracy gate; adopt only if it wins by >3 percentage points at comparable cost.

Pass gate for terrain enrichment (Phase 2 of Lane B):

| Metric | Threshold |
|---|---|
| Per-field accuracy vs ground truth | ≥95% `blocks_movement`; ≥90% on others |
| Deterministic re-run with same cache | Bit-identical sidecar file |
| Cost for one full pass | <$0.05 with gpt-4o-mini |
| Hallucination spot-check (5 random) | Zero invented fields |

## Sequencing

1. **First**, validate the HTML pivot is real for the highest-value file — `weapon_parser.py`. Build a small spike that extracts the table fields for the 50 weapons in `data/raw/weapon/`, compare to `data/parsed/edges.json` and current weapon nodes. Decide go/no-go on Lane A as a whole.
2. If go, refactor `weapon_parser.py` and `spell_parser.py` first (simplest tables, biggest closed GAPs).
3. Then `_options.py` as a feature-flagged side-by-side parse, diff-driven swap.
4. Inspect army-list pages, decide whether `army_list_parser.py` joins Lane A or stays on regex.
5. Only **after** Lane A lands, start Lane B with the terrain enrichment spike.
6. Treat `ScrapeGraphAI` benchmarking as an explicit Phase 3 of Lane B; do not pre-commit to adoption.

## Critical files

- `pipeline/scraper/parsers/base_parser.py` — add a `BeautifulSoup` view helper alongside `_get_next_data`; keep both available to subclasses.
- `pipeline/scraper/parsers/weapon_parser.py` — first Lane A target.
- `pipeline/scraper/parsers/spell_parser.py` — second Lane A target; can also drop the dual extraction strategy.
- `pipeline/scraper/parsers/_options.py` — third Lane A target; feature-flagged.
- `pipeline/scraper/parsers/army_list_parser.py` — inspect, then decide.
- `pipeline/scraper/parsers/terrain_parser.py` — Lane B first target (unchanged in Lane A).
- `pipeline/scraper/parsers/__init__.py` — coordinator; `_derive_clarifies_amends` is Lane B target 2.
- `pipeline/run_pipeline.py` + `Makefile` — wire optional `enrich-*` stages once Lane B reaches them.
- `pyproject.toml` — no new core deps for Lane A; `scrapegraphai` only as `[project.optional-dependencies] enrich` if it wins the head-to-head.

## Verification

- **Lane A unit tests**: for each refactored parser, run against the existing `data/raw/{type}/` corpus, diff resulting `data/parsed/*.json` against the regex baseline; expected diffs are *new fields populated* + *typed UNLOCKS_* edges directly*, not removed fields. Any removed fields are a regression.
- **Lane A integration**: full `make parse && make build-graph` against fresh `data/raw/`; assert node/edge counts move only in the expected direction.
- **Lane B unit tests**: `tests/unit/scraper/enrichers/test_terrain_enricher.py` mocking the LLM call; assert cache stability and silent fallback when `OPENAI_API_KEY` missing.
- **Lane B integration**: `tests/integration/test_enrichment_pipeline.py` on a 3-page fixture with a frozen LLM cassette.
- **Lane B evaluation**: `tests/eval/terrain_accuracy.py` vs the slug-table ground truth; gates promotion.
- **Reproducibility**: `make parse && make enrich-terrain` twice → identical sha256.

## Risks

| Risk | Mitigation |
|---|---|
| HTML structure changes (Contentful CMS template update) silently breaks selectors | Lane A keeps the JSON-richtext path as fallback per field; integration tests will flag missing fields |
| `_options.py` HTML refactor regresses army-build correctness | Side-by-side parse with full-corpus diff before swap; behind feature flag during the diff phase |
| Hallucinated terrain booleans | Defer behind Phase 2 accuracy gate; rollback by deleting sidecar |
| Cost runaway in Lane B | Mandatory budget pre-flight; content-hash cache; skip silently without API key |
| Scope creep into `_options.py` LLM enrichment | Explicit "never without a fresh decision" on that file |
| Vendor lock-in (OpenAI) | LangChain abstraction; Ollama via `langchain-ollama` (already in dev extras) for local baseline |

## Rejected alternatives

- Replace `requests`+`bs4` crawler with `SmartScraperGraph` or `llm-scraper`. Recurring LLM cost on every `make scrape`, no gain on a static `__NEXT_DATA__` site, breaks determinism, breaks offline contributors.
- Adopt `llm-scraper` at all. Wrong language for this monorepo, wrong tool for the source format.
- Adopt `ScrapeGraphAI` as default scraper. Same reasons; also breaks reproducibility.
- Skip the HTML pivot and use LLMs to fill weapon/spell stats. More expensive, less reliable, and unnecessary — the data is already in clean HTML tables.
- Refactor `_options.py` blind (no side-by-side diff). Too load-bearing for army-construction validity to swap atomically.
- Spike Lane B on `_options.py` or weapon stats first. Wrong risk profile.
