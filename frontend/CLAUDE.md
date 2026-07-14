# CLAUDE.md — frontend/

Scoped context for the TanStack Start frontend (chat UI + graph visualisation).
For project overview and coding conventions, see [`../CLAUDE.md`](../CLAUDE.md).

---

## Stack

| Tool | Purpose |
|---|---|
| TanStack Start | SSR/SPA framework (file-based routing) |
| TanStack Router | Type-safe client routing |
| Tailwind CSS | Styling |
| HeroUI | Component library (`@heroui/react`) |
| Biome | Linter + formatter (replaces ESLint + Prettier) |
| Vitest | Unit + component tests |
| Playwright | End-to-end tests |
| Paraglide (inlang) | i18n — localised routing + message formatting |
| pnpm | Package manager — **never use npm or yarn** |

---

## Architecture: Feature-Sliced Design (FSD)

```
src/
  routes/         ← TanStack Router file-based routes (page entry points only)
  widgets/        ← composite blocks combining entities + features (e.g. graph-viewer)
  features/       ← self-contained feature slices (e.g. chat/)
  entities/       ← domain models + their UI
  shared/         ← cross-cutting utilities, UI primitives, API client, config
  paraglide/      ← GENERATED — do not edit manually; regenerated on dev/build
```

Each slice owns its `ui/`, `model/`, and `api/` subdirs. Slices may import from `shared/` but not from sibling features. Import rules are enforced via Biome `noRestrictedImports`.

---

## i18n (Paraglide)

- Messages live in `messages/` (one JSON file per locale).
- `src/paraglide/` is auto-generated — never edit it directly.
- Run `pnpm dev` or `pnpm build` to regenerate after adding/changing message keys.
- URL routing is localised through the Paraglide Vite plugin and router `rewrite` hooks.

---

## Chat / streaming

- Chat calls the Python backend's `/chat` endpoint.
- Responses are streamed using the **Vercel AI SDK** (`useChat` hook, SSE format).
- Backend produces Vercel AI SDK-compatible SSE — see `../backend/api/vercel_stream.py`.
- `src/shared/api/query/` wires TanStack Query (provider, SSR integration, devtools) — not yet used by any route.
- Chat talks to the backend via the Vercel AI SDK `DefaultChatTransport` pointing at `${env.apiUrl}/chat/`; `src/features/chat/` owns the chat feature.
- A typed REST client for the `/graph` endpoints is implemented in `src/shared/api/graph.ts`; the graph viewer lives in `src/widgets/graph-viewer/` (route `src/routes/graph.tsx`).

---

## Common commands

```bash
pnpm dev          # start dev server (hot-reload)
pnpm build        # production build
pnpm test         # Vitest unit/component tests
pnpm test:e2e     # Playwright end-to-end (requires running dev server)
pnpm check        # Biome lint + format check
pnpm format       # auto-format with Biome
```

---

## Adding a route

Create a file in `src/routes/`. TanStack Router auto-registers it. Update `routeTree.gen.ts` by running the dev server (it regenerates automatically).

## HeroUI conventions

- All UI is built with [`@heroui/react`](https://www.heroui.com/) components (Card, Button, Alert, TextArea, etc.).
- Styling is done via Tailwind v4 utility classes alongside HeroUI's variant props.
- Components land in `src/shared/ui/` (or the relevant feature slice if tightly coupled).
