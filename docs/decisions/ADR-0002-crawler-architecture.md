# ADR-0002 — Crawler Architecture: Seeding Strategy

| Field       | Value                          |
|-------------|--------------------------------|
| **Status**  | Accepted                       |
| **Date**    | 2026-02-20                     |
| **Deciders**| Project author                 |
| **Tags**    | crawler, data-ingestion, scraping |

---

## Context

The knowledge graph is built from the community wiki at [tow.whfb.app](https://tow.whfb.app). Full coverage is required: core rules, army-specific rules, unit profiles, weapons, magic, special rules, FAQs, and errata.

Two seeding strategies were under consideration:

**Option A — Breadth-first from Table of Contents**
Start at `/`, extract all internal links, enqueue them, and crawl recursively.

**Option B — Sitemap-first**
Fetch `sitemap.xml` or equivalent structured sitemaps, extract the full URL inventory, then fetch each page.

### Live investigation findings (2026-02-20)

The site was inspected directly. Key findings:

**`robots.txt`**:
```
User-agent: *
Allow: /*
Disallow: /api/*
Disallow: /apps/*
Disallow: /public/apps/*
Disallow: /regenerate
```
All content pages are permitted. No ethical or technical barrier to crawling.

**The TOC at `/`** is a single static HTML page that contains, in structured form:
- Every core rules section and every sub-page listed hierarchically.
- All 19 army URLs as an explicit list under "Army Index" (`/army/{slug}`).
- Direct links to `/faq` and `/errata`.
- A footer link to `/sitemap`.

**`/sitemap/rules`** is an A-Z alphabetical flat index covering ~1,500+ individual rule page links. It contains entries the TOC does not surface at the top level — notably army-specific magic items and sub-rules listed individually.

**`/sitemap/armies`** exists and contains an A-Z unit index covering all `/unit/{slug}` pages across all armies.

**Unit pages (`/unit/{slug}`)** are not linked from the TOC or `/sitemap/rules`. They only appear as links inside `/army/{slug}` pages and in `/sitemap/armies`. A strategy that seeds only from the TOC would miss them unless link-following is also performed.

**FAQ structure**: organised per topic at `/faq/{topic}` (e.g. `/faq/shooting`, `/faq/magic`, `/faq/empire-of-man`). Each answer carries explicit source attribution including version number.

**Errata**: available at `/errata`. Errata content is also integrated inline into the relevant rule pages — rule page text is therefore authoritative and already reflects current errata.

---

## Decision

**Dual-seed from TOC + sitemaps, with internal link-following as a completeness check.**

Neither Option A nor Option B alone is sufficient. The site provides three complementary URL inventories; all three are used as seeds, and internal link-following provides a safety net for any orphan pages.

### Crawl seed strategy

```
Seed 1:  tow.whfb.app/                →  all section URLs + all 19 army URLs + /faq + /errata
Seed 2:  tow.whfb.app/sitemap/rules   →  A-Z flat index; completeness check for core rules
Seed 3:  tow.whfb.app/sitemap/armies  →  A-Z unit index; all /unit/{slug} pages
Follow:  all <a href="/..."> internal links found on each fetched page
Exclude: /api/*, /apps/*, /public/apps/*, /regenerate   (per robots.txt)
         External domains: old-world-builder.com, S3 PDF links, whfb.app (parent site)
```

### URL deduplication

All discovered URLs are normalised (strip fragment, trailing slash canonical) and added to a `seen` set before enqueueing. This ensures each page is fetched exactly once regardless of how many times it appears across the three seeds and link-following.

### Page type classification

The URL path structure encodes the page type, enabling downstream parser selection before fetching content:

| URL pattern | Page type | Parser |
|-------------|-----------|--------|
| `/` | Table of Contents | TOC parser (seed only) |
| `/sitemap/*` | Sitemap index | Sitemap parser (seed only) |
| `/{section}/{slug}` | Rule page | Rule parser |
| `/army/{slug}` | Army index | Army parser |
| `/army/{slug}/reference/` | Stat reference chart | Reference chart parser |
| `/unit/{slug}` | Unit profile | Unit parser |
| `/faq/{topic}` | FAQ section | FAQ parser |
| `/errata` | Errata page | Errata parser |
| `/magic-items/{slug}` | Magic item | Rule parser |
| `/special-rules/{slug}` | Special rule | Rule parser |
| `/the-lores-of-magic/{slug}` | Lore/spell list | Rule parser |

### Hardcoded army slug fallback

If the TOC ever fails to parse, the 19 army slugs confirmed during investigation can serve as a hardcoded seed:

```python
ARMY_SLUGS = [
    "beastmen-brayherds", "chaos-dwarfs", "daemons-of-chaos",
    "dark-elves", "dwarfen-mountain-holds", "empire-of-man",
    "grand-cathay", "high-elf-realms", "kingdom-of-bretonnia",
    "lizardmen", "ogre-kingdoms", "orc-and-goblin-tribes",
    "realms-of-men", "regiments-of-renown", "skaven",
    "tomb-kings-of-khemri", "vampire-counts", "warriors-of-chaos",
    "wood-elf-realms",
]
```

### Politeness

- Minimum 1-second delay between requests (`time.sleep(1)` or `asyncio.sleep(1)`).
- `User-Agent` header identifies the project: `WarhawmerTOW-GraphRAG-Thesis/1.0`.
- Crawl is run once and results persisted; no live crawling at query time.

---

## Consequences

### Positive
- Deterministic and reproducible: the same three seed URLs produce the same URL inventory on every run, making the crawl verifiable and reportable in the thesis methodology section.
- Complete coverage: core rules, army indexes, unit profiles, FAQs, and errata are all reachable via the seed set without relying solely on link-following.
- Structural metadata comes for free: the URL path determines page type, which determines parser, before the page is even fetched.
- Efficient: ~3 seed fetches produce a near-complete URL inventory before any crawling begins; the crawler does not need to discover structure iteratively.

### Negative / accepted trade-offs
- If the site restructures its URLs, both the seed list and the page-type classifier must be updated.
- `/sitemap/armies` was not directly fetchable during investigation (required appearing in prior search results); it was confirmed to exist via Google's index. If it remains inaccessible, `/unit/{slug}` coverage falls back entirely to link-following from `/army/{slug}` pages, which is sufficient.

### Constraints imposed on other decisions
- The crawler must emit a structured record per page that includes the canonical URL as a required field — this URL becomes the `source_url` property on Neo4j nodes and the citation anchor in chatbot responses.
- PDF links (GW's S3 bucket) must be recorded as metadata but not fetched or parsed.
- External links (old-world-builder.com) must not be followed.

---

## Addendum — Implementation findings (2026-04-14)

During parser implementation, the site was re-inspected to validate the data
extraction strategy.  The following **significant architectural discovery**
supersedes the HTML-scraping assumption made in this ADR.

### The site is a Next.js + Contentful CMS application

`tow.whfb.app` is **not** a server-rendered HTML site in the traditional sense.
It is a Next.js application backed by Contentful as a headless CMS.  Every page
is pre-rendered via **Incremental Static Regeneration (ISR)** and includes the
complete Contentful entry data embedded in the HTML as a JSON blob:

```html
<script id="__NEXT_DATA__" type="application/json">
  {"props": {"pageProps": {"entry": {...}, "rulesByType": [...], ...}}, ...}
</script>
```

This `__NEXT_DATA__` tag contains the full Contentful response including all
linked entries (resolved at build time), richtext documents, and metadata.
**No BeautifulSoup DOM traversal is needed.**  A single regex extract +
`json.loads()` gives complete, structured data for every page.

### ISR fallback pages

When a page is requested for the first time (before ISR pre-renders it),
Next.js returns a **fallback HTML** where `isFallback: true` in the
`__NEXT_DATA__` JSON and `pageProps` is an empty object `{}`.

The crawler must detect this and retry the page.  Detection:

```python
data = json.loads(next_data_blob)
if data.get("isFallback"):
    # page not yet rendered — schedule a retry
```

Pages that are not yet pre-rendered can be triggered by visiting them in a
browser (or making an HTTP request), after which ISR builds the page and
subsequent requests receive the full data.

### Contentful content types

The site uses three primary Contentful content types:

| Content type    | URL pattern | Parser |
|-----------------|-------------|--------|
| `association`   | `/army/{slug}` | ArmyParser |
| `armyListEntry` | `/unit/{slug}` | UnitParser |
| `rule`          | everything else | RuleParser, CoreRuleParser, SpellParser, MagicItemParser, WeaponParser |

The `rule` content type is distinguished by `entry.fields.ruleType[0].fields.slug`:

| `ruleType.slug` | Parser dispatched |
|-----------------|-------------------|
| `special-rules` | RuleParser → Rule node |
| `troop-types-in-detail` | RuleParser → TroopType node |
| `weapons-of-war` | WeaponParser |
| `the-lores-of-magic` | SpellParser |
| `magic-items` / `magic-items-and-abilities` | MagicItemParser |
| anything else (section slug) | CoreRuleParser |

**Routing is done by URL pattern** in `parsers/__init__.py`, which is more
reliable than content-type inspection at runtime because the crawler classifies
URLs before fetching them.

### Embedded content in richtext bodies

Several Contentful content types embed child entries inside richtext `body`
fields as `embedded-entry-block` nodes.  The child data is under
`block.data.<key>[]`:

| Page type | Richtext key | Content |
|-----------|-------------|---------|
| Lore of magic | `data.spell[]` | Individual spell objects |
| Magic items | `data.magicItem[]` | Individual magic item objects |

These embedded arrays are the **only** source for spell and magic item data —
there are no individual pages per spell or magic item.

### FAQ and Errata page structure

The FAQ (`/faq`) and errata (`/errata`) pages do **not** use a single `entry`
key.  Instead, `pageProps.entries` is a flat array of Q&A / correction objects.
Each entry has `{fields: {question/name, body (richtext), source, slug}}`.

---

## References

- Live `robots.txt`: <https://tow.whfb.app/robots.txt>
- TOC page inspected: <https://tow.whfb.app/>
- Rules sitemap inspected: <https://tow.whfb.app/sitemap/rules>
- Armies sitemap confirmed: <https://tow.whfb.app/sitemap/armies>
