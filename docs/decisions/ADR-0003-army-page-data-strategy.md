# ADR-0003 — Army Page Data Strategy: Wiki-only vs. Hybrid with GitHub JSONs

| Field       | Value                          |
|-------------|--------------------------------|
| **Status**  | Accepted                       |
| **Date**    | 2026-02-20                     |
| **Deciders**| Project author                 |
| **Tags**    | data-ingestion, army-lists, units |

---

## Context

Army and unit data are the most structured content on the wiki. An alternative acquisition route was considered: supplementing the scraped HTML with structured JSON files published to GitHub by the community (e.g. the Old World Builder project), which encode unit stats, points costs, and options in machine-readable form.

The hypothesis to evaluate was: **does the wiki provide sufficient structured data for all army and unit information, or are the JSONs necessary to fill gaps?**

### Live investigation findings (2026-02-20)

The following page types were inspected directly:

#### `/army/{slug}` — Army index pages

Each army page contains, in static HTML:

- **Army-specific special rules** — every rule listed by name, each a hyperlink to its full-text page at `/special-rules/{slug}`. These hyperlinks are graph edges.
- **Army-specific weapons of war** — same pattern, links to `/weapons-of-war/{slug}`.
- **Lores of magic** — links to `/the-lores-of-magic/{slug}`.
- **Magic items** — link to `/magic-items/{slug}-magic-items`.
- **Complete unit roster** — organised by category (Named Characters, Characters, Infantry, Cavalry, Chariots, Monsters, War Machines, Mounts), each unit a link to `/unit/{slug}`.
- **Full stat reference table** — a plain HTML `<table>` containing M/WS/BS/S/T/W/I/A/Ld and Troop Type for every unit and sub-profile (e.g. crew, mounts, split profiles). Parsed trivially with BeautifulSoup.
- **PDF link** — GW's official S3 bucket URL, useful as a citation reference, not as a data source.

Example stat row from the Skaven army page:
```
Clanrat | 5 | 3 | 3 | 3 | 3 | 1 | 4 | 1 | 4 | Regular Infantry
```

#### `/unit/{slug}` — Unit profile pages

Each unit page contains, in plain text:

```
Unit Category: Infantry
Troop Type: Regular Infantry
Base Size: 25 x 25 mm
Unit Size: 20–40
Hand weapons and light armour

Any unit may:
  Thrusting spears (+1 point per model)
  Shields (+1 point per model)
  Upgrade one model to a Clawleader (champion) (+7 points per unit)
  Upgrade one model to a standard bearer (+5 points per unit)
  Upgrade one model to a musician (+5 points per unit)
  Have one weapon team

Special Rules: Close Order · Horde · Scurry Away · Warband
```

Points costs, base sizes, unit size constraints, upgrade trees, and special rule tags are all present, in clean text, without JavaScript rendering.

Special rules are listed as plain text tokens. Each token corresponds to a named node in the graph (at `/special-rules/{slug}`), making them parseable as edges.

#### `/faq/{topic}` and `/errata`

FAQ pages are structured per game topic. Each answer carries explicit source attribution:
```
Source: Official Warhammer: The Old World FAQ & Errata - Version 1.5.2
```
Army-specific FAQs exist at paths like `/faq/empire-of-man`, `/faq/orc-and-goblin-tribes`. Errata content is also integrated inline into rule pages, so the rule pages themselves are authoritative.

### Data completeness matrix

| Data type | Wiki provides | GitHub JSONs would add |
|-----------|---------------|------------------------|
| Stat lines (M/WS/BS/S/T/W/I/A/Ld) | ✅ HTML table on `/army/{slug}` | Nothing |
| Points costs and upgrade options | ✅ `/unit/{slug}` prose | Nothing |
| Special rule full text | ✅ `/special-rules/{slug}` own page | Nothing |
| Army composition rules | ✅ `/warhammer-armies/{slug}-army-list` | Nothing |
| Magic items text | ✅ `/magic-items/{slug}` own page | Nothing |
| FAQ with source versioning | ✅ `/faq/{topic}`, versioned per answer | Nothing |
| Errata | ✅ `/errata` + integrated inline | Nothing |
| Cross-page hyperlinks (graph edges) | ✅ Native `<a href>` in HTML | Not present in flat JSON |
| **Translations** | ❌ Wiki is English-only | ⚠️ Possible, if JSONs contain them |

---

## Decision

**Wiki-only. The GitHub JSONs are not used.**

Every piece of data required to build the knowledge graph — stats, points costs, upgrade options, special rule text, lore text, magic item text, FAQ content, and errata — is available in the scraped HTML. The JSONs would add no new data for the English-language content the graph is built on.

The one hypothetical use case for JSONs is **translations** (Spanish or other language names for units and rules). This is rejected for two reasons:

1. The game's canonical rules are English-only; no player queries the system using Spanish unit names.
2. The project's language policy (defined in the repository) requires all data, code, and documentation to be in English. Spanish appears only in i18n fields of data files, which are not part of the knowledge graph.

### Unit page discovery

Unit pages at `/unit/{slug}` are **not** listed in the TOC or the rules sitemap. They are discovered via two routes (see ADR-0002):

1. Internal links from `/army/{slug}` pages (each army page lists all its units as hyperlinks).
2. `/sitemap/armies`, which provides a complete A-Z unit index as a completeness check.

This is noted here because it directly informs parser design: the army page parser must emit unit URLs as crawler tasks, not just graph data.

### Parser design implications

Four distinct parsers are required:

**Army parser** (`/army/{slug}`):
- Emit: `Army` node with properties `{name, slug, source_url}`.
- Emit: edges `HAS_SPECIAL_RULE`, `HAS_WEAPON`, `HAS_LORE`, `HAS_MAGIC_ITEMS` by following anchor hrefs.
- Emit: `HAS_UNIT` edges from army to each unit.
- Emit: crawler tasks for each `/unit/{slug}` found.
- Parse: stat reference table as a structured dict keyed by unit name.

**Unit parser** (`/unit/{slug}`):
- Emit: `Unit` node with properties `{name, slug, source_url, category, troop_type, base_size, unit_size_min, unit_size_max, default_equipment}`.
- Emit: `HAS_SPECIAL_RULE` edges for each special rule token in the special rules list.
- Emit: `HAS_UPGRADE` edges for each option line with `{points_cost, per_model}` properties.

**FAQ parser** (`/faq/{topic}`):
- Emit: `FAQ` nodes with properties `{question, answer, source_version, topic, source_url}`.
- Emit: `CLARIFIES` edges to rule nodes where the answer references a named rule.

**Errata parser** (`/errata`):
- Emit: `Errata` nodes with properties `{rule_name, amendment_text, source_version, source_url}`.
- Emit: `AMENDS` edges to the relevant rule nodes.

---

## Consequences

### Positive
- Single data source simplifies the ingestion pipeline: one scraper, no JSON fetch step, no version synchronisation between two sources.
- HTML hyperlinks are the primary source of graph edges; this is more reliable than inferring relationships from flat JSON field values.
- The wiki integrates errata inline, so scraped rule text is always current — no need to apply a patch layer from a separate errata JSON.
- Reproducibility: the corpus is fully defined by the seed URLs in ADR-0002; no external JSON repository versioning to manage.

### Negative / accepted trade-offs
- If unit data that is not visible in the rendered HTML exists only in a JavaScript bundle or API response, it would be missed. Investigation showed no evidence of this; all content rendered as static HTML.
- The wiki is community-maintained; errors or omissions in the wiki will propagate to the graph. The official PDF (linked on each army page) serves as the ground truth for resolving any discrepancy, but is not parsed.

### Constraints imposed on other decisions
- The unit parser must handle split profiles (e.g. cavalry rider + mount, chariot + crew) as separate stat sub-nodes linked by a `SPLIT_PROFILE_OF` edge.
- Points costs parsed from unit pages must be stored as `Upgrade` node properties, not as properties of the `Unit` node itself, since the same unit can have multiple mutually exclusive upgrade paths.
- The `source_url` property on every node is mandatory and must be the canonical wiki URL — it is the citation anchor surfaced to the user in chatbot responses.

---

## References

- Skaven army page inspected: <https://tow.whfb.app/army/skaven>
- Grand Cathay army page inspected: <https://tow.whfb.app/army/grand-cathay>
- Clanrats unit page confirmed via search: <https://tow.whfb.app/unit/clanrats>
- FAQ structure confirmed: <https://tow.whfb.app/faq/shooting>, <https://tow.whfb.app/faq/magic>
- Errata page confirmed: <https://tow.whfb.app/errata>
