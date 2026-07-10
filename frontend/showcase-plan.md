# Frontend Showcase Plan

> **Goal**: a working local demo where a visitor asks a rules/army question, sees retrieved graph context, and gets a real streaming answer with citations — all over a polished Warhammer-themed UI.
>
> **Priorities**: (1) Stability, (2) End-to-end completion over depth. Graph visualisation is deliberately out of scope.
>
> **Quality bar**: Zod at validation boundaries, `safeParse` for leniency, type guards for narrowing, no `as` casts, no `any`, `unknown` over `any`. Modern 2026 patterns.
>
> **Status**: Phase A, B, C, D complete ✅ — Showcase frontend ready

---

## Architecture decisions (locked)

### Lenient reader model

The frontend may receive `data-*` SSE event types it doesn't know how to parse. It must drop those silently without crashing the stream. This is enforced at the render boundary via `safeParse`, **not** via `useChat`'s `dataPartSchemas` (which would throw and abort the stream on validation failure).

**Resolution**: validate at render time with `z.array(graphSourceSchema).safeParse(part.data)`: on success, narrow to `GraphSource[]` and render; on failure, drop silently with `console.warn`. We do **not** pass a schema to `useChat`'s `dataPartSchemas` option, because that would abort the stream on validation failure. The schema wiring is documented in `graph-source.ts` for the day we switch to strict-mode SDK validation.

### Unknown part types

Any `data-${string}` part type that isn't `"data-sources"` falls through to `return null` in the parts map loop — no crash, no render. The SDK's transport-level `uiMessageChunkSchema` accepts any `data-${string}` with `data: unknown` and a strict top-level object, so unknown `data-*` events never throw at the transport level.

### Empty sources

When the backend sends a `data-sources` event with an empty array (valid against the schema), render the "Sources" label with a muted "(no sources retrieved)" message. This is more transparent for the thesis demo — shows the viewer that retrieval was attempted.

---

## Phase A — Source citation rendering (THE critical path)

The visual proof that GraphRAG retrieval happened. Without this, the demo is just a chatbot.

- [x] **A1** — Zod schema + type + lenient parser
  - File: `src/features/chat/model/graph-source.ts` (**new**)
  - `graphSourceSchema` uses `.string().nullish().transform(v => v ?? undefined)` for optional fields so `null` values do not cause us to drop an otherwise valid source array. `source_url` is a plain `string` (not `.url()`), with URL validation done at render time.
  - `GraphSource = z.infer<typeof graphSourceSchema>`
  - `parseGraphSources(data: unknown): GraphSource[] | null` — `z.array(graphSourceSchema).safeParse(data)`, success → return narrowed array, failure → `console.warn` + return `null`
  - `chatDataPartSchemas` wiring is documented in the file but kept internal; exporting it produced an unused export and would only be useful if we switch to strict SDK validation.

- [x] **A2** — `SourcesList` pure component
  - File: `src/features/chat/ui/SourcesList.tsx` (**new**)
  - `function SourcesList({ sources }: { sources: GraphSource[] })`
  - Renders i18n "Sources" label + HeroUI `Chip` per source
  - Empty array renders "(no sources retrieved)" muted message
  - Each chip: `source.id` as key, HeroUI `Tooltip` with `source.text` on hover, `source.source_url` → chip wrapped in `<a>`
  - Kept internal to the feature; **not** exported from `src/features/chat/index.ts` to avoid an unused public export.

- [x] **A3** — Render `data-sources` parts in `ChatInterface`
  - File: `src/features/chat/ui/ChatInterface.tsx` (edit)
  - Add `case "data-sources"` before the `return null` fallback
  - `const sources = parseGraphSources(part.data); if (sources === null) return null; return <SourcesList sources={sources} />`
  - No `dataPartSchemas` passed to `useChat`
  - Part key uses `part.id` (stable SDK-assigned), not array index

- [x] **A4** — Extend `ChatMother.sseStream` with `data-sources` support
  - File: `src/test/mothers/chat.mother.ts` (edit)
  - Optional `sources?: GraphSource[]` param (typed, imports from `#/features/chat/model`)
  - Emits `data: {"type":"data-sources","id":"src_${id}","data":[...]}` before `text-end`
  - Backward compatible (existing callers pass no opts)

- [x] **A5** — Unit tests: `SourcesList` + integration
  - `src/features/chat/ui/SourcesList.test.tsx` (**new**): renders chips for valid `GraphSource[]`; renders "(no sources retrieved)" for empty array; wraps link chips correctly
  - `src/features/chat/ui/ChatInterface.test.tsx` (edit): 3 new tests — `data-sources` with sources renders chips; malformed `data-sources` (bad shape) renders nothing without crashing; empty `data-sources` renders "No sources retrieved"

### Phase A verification

- `pnpm format --write` ✅
- `pnpm check` (Biome lint + format) ✅
- `pnpm typecheck` ✅
- `pnpm test` (19 tests across 2 files) ✅
- `pnpm knip` ✅ except for the pre-existing `ErrorBoundary` unused export in `src/shared/ui/index.ts`.

---

## Phase B — App shell + visual polish

The current page is a bare `p-8` div. A visitor lands and sees a chat box with no context.

- [x] **B1** — `AppHeader` component
  - File: `src/shared/ui/AppHeader.tsx` (**new**), `src/shared/ui/index.ts` (edit)
  - Cinzel-display `m.app_title()` title, `m.app_subtitle()` subtitle, `ThemeToggle` right-aligned
  - Sticky top, border-bottom, `shrink-0`

- [x] **B2** — Responsive flex layout
  - Files: `src/routes/index.tsx` (edit), `src/features/chat/ui/ChatInterface.tsx` (edit)
  - Page: `h-screen flex flex-col`
  - Header: `shrink-0`
  - Chat container: `flex-1 min-h-0`
  - `ChatInterface` outer div: `h-full` replaces `h-[calc(100vh-8rem)]`
  - Padding: `px-4 sm:px-8`

- [x] **B3** — Example query chips in empty state
  - Files: `src/features/chat/ui/ChatInterface.tsx` (edit)
  - Replace `📜` block with 3 accessible `<button>` cards (clicking calls `sendMessage({ text: query })`)
  - Uses `lucide-react` `Scroll` icon for visual accent
  - i18n keys already added in Phase A: `app_subtitle`, `chat_sources_label`, `chat_no_sources`, `chat_example_1/2/3`, `chat_example_prompt`

- [x] **B4** — Visual polish
  - Files: `src/features/chat/ui/ChatInterface.tsx`, `src/styles.css`
  - Source chips use HeroUI `Chip color="accent" variant="soft"`
  - User message bubble uses `bg-accent` with plain white text (no prose override)
  - Darkened `--muted` in light mode to meet WCAG 2 AA contrast
  - `SourcesList` separator: `border-t border-border/50 mt-2 pt-2`

---

## Phase C — Stability hardening

- [x] **C1** — Mobile width pass
  - File: `src/features/chat/ui/ChatInterface.tsx`
  - Verified responsive classes: `px-4 sm:px-8`, `max-w-4xl mx-auto`, `max-w-[80%]` bubbles, `flex-wrap` chips

- [x] **C2** — Streaming + sources flicker check
  - File: `src/features/chat/ui/ChatInterface.tsx`
  - `data-sources` parts are keyed by `part.id` (stable SDK id); no array-index key that would re-render on each `text-delta`

- [x] **C3** — Unknown-malformed part resilience
  - File: `src/features/chat/ui/ChatInterface.tsx`
  - Malformed `data-sources` (fails `safeParse`) → `return null`, stream continues, text still renders
  - Unknown `data-*` type → `return null`, no crash
  - Covered by unit test "drops malformed data-sources parts without crashing"

---

## Phase D — Demo regression tests

- [x] **D1** — Update e2e empty-state
  - File: `tests/e2e/chat.spec.ts` (edit)
  - Assert empty-state title + all 3 example query buttons visible
  - Added test: clicking an example query sends it and renders the reply

- [x] **D2** — Add e2e sources rendering
  - File: `tests/e2e/chat.spec.ts` (edit)
  - Intercept with `ChatMother.sseStream(FEAR_REPLY, { sources: [...] })`
  - Assert "Sources" label and source chip buttons ("fear", "flaming-attacks") visible

- [x] **D3** — Update a11y tests
  - File: `tests/e2e/a11y.spec.ts` (edit)
  - Empty-state, with-messages, and with-sources scans all pass (0 axe-core violations)
  - Fixed contrast issues surfaced by the scans: `--muted` darkened, user message prose override removed

### Phase B/C/D verification

- `pnpm format --write` ✅
- `pnpm check` (Biome lint + format) ✅
- `pnpm typecheck` ✅
- `pnpm test` (19 Vitest tests) ✅
- `pnpm test:e2e` ✅ — 9 Playwright tests passed
- `pnpm knip` ✅ — no unused exports or dependencies

---

## Dependency graph

```
A1 (schema) ──► A2 (SourcesList) ──┐
A1 (schema) ──► A4 (mother)  ──────┤
                                   ├─► A3 (render) ──► A5 (tests) ──┐
                                   │                                │
B1 (header) ──► B2 (layout) ───────┤                                │
                                   │                                │
B3 (example chips) ──► ─────────── ┤                                │
                                   │                                │
B4 (polish) ──────────► ─────────── ┤                                │
                                   │                                │
C1, C2, C3 (stability) ──► ──────── ┘                                │
                                                                    │
                                                                    ├─► D1, D2, D3 (e2e) ──► done
                                                                    │
```

A1 is the foundation (schema + type everyone imports). A2 and A4 depend on A1. A3 depends on A2. A5 depends on A3 + A4. B1+B2 are sequential. B3 depends on B2 (layout). Everything converges into D.

---

## i18n keys to add

| Key | en | es |
|---|---|---|
| `app_subtitle` | "GraphRAG-powered rules assistant" | "Asistente de reglas potenciado por GraphRAG" |
| `chat_sources_label` | "Sources" | "Fuentes" |
| `chat_no_sources` | "No sources retrieved" | "No se recuperaron fuentes" |
| `chat_example_1` | "What happens when a unit with Regeneration is hit by Flaming Attacks?" | "¿Qué ocurre cuando una unidad con Regeneración recibe Ataques Flamígeros?" |
| `chat_example_2` | "Tell me about the Blood Knights" | "Háblame de los Caballeros de Sangre" |
| `chat_example_3` | "How does Fear work?" | "¿Cómo funciona el Miedo?" |
| `chat_example_prompt` | "Try one of these:" | "Prueba una de estas:" |

Running `pnpm dev` or `pnpm build` regenerates `src/paraglide/` automatically.

---

## Files touched (summary)

| File | Type | Phase |
|---|---|---|
| `src/features/chat/model/graph-source.ts` | **new** | A1 |
| `src/features/chat/ui/SourcesList.tsx` | **new** | A2 |
| `src/features/chat/ui/SourcesList.test.tsx` | **new** | A5 |
| `src/features/chat/ui/ChatInterface.tsx` | edit | A3, B2, B3, B4, C1, C2, C3 |
| `src/features/chat/ui/ChatInterface.test.tsx` | edit | A5 |
| `src/test/mothers/chat.mother.ts` | edit | A4 |
| `src/shared/ui/AppHeader.tsx` | **new** | B1 |
| `src/shared/ui/index.ts` | edit | B1 (barrel) |
| `src/routes/index.tsx` | edit | B2 |
| `src/routes/__root.tsx` | edit | B1 (barrel import) |
| `messages/en.json` | edit | B3 |
| `messages/es.json` | edit | B3 |
| `src/styles.css` | edit | B4 |
| `knip.config.ts` | edit | B1 (cleanup ignored deps) |
| `tests/e2e/chat.spec.ts` | edit | D1, D2 |
| `tests/e2e/a11y.spec.ts` | edit | D3 |

**4 new files, 12 edits. No dependency changes, no backend changes, no routing changes, no `as` casts, no `any`.**

---

## Out of scope (cut for depth)

- Graph visualisation (`/graph/{id}` route, `widgets/graph-viewer/` slice)
- Multi-conversation sidebar
- Message timestamps
- "Copy message" button
- Per-message "regenerate up to here"
- Message virtualisation (`@tanstack/react-virtual`)
- Real graph viewer widget
- Typed REST client for `/graph` endpoints (stays unimplemented until graph viewer starts)

---

## Verification commands (run after each phase)

```bash
pnpm check         # Biome lint + format check
pnpm typecheck     # tsc --noEmit
pnpm test          # Vitest unit/component tests
pnpm test:e2e      # Playwright end-to-end (auto-starts dev server or set APP_URL)
```

All four must be green before the plan is considered complete.