# Whfb-tow-companion — Frontend

Conversational assistant + graph visualisation UI for Warhammer: The Old World.
Built with TanStack Start, HeroUI, Paraglide i18n, and Feature-Sliced Design.

## Features

- **Streaming chat** over the Vercel AI SDK protocol — calls the Python backend's `/chat` endpoint with `useChat` from `@ai-sdk/react`.
- **Markdown rendering** of assistant replies with GFM support and `rehype-sanitize` XSS sanitisation.
- **Bilingual UI** (English + Spanish) via Paraglide — locale encoded in the URL.
- **Dark / light theme toggle** powered by `next-themes`.
- **Abort-on-unmount** — leaving the page mid-stream cancels the request client-side.
- **(Coming soon)** Graph visualisation of the Neo4j knowledge graph.

## Prerequisites

- **Node.js** >= 24.13.1 (see `.node-version`).
- **pnpm** >= 10.33.2 (pinned via the `packageManager` field in `package.json`).
- The **Python backend** running locally — see [`../README.md`](../README.md) for setup. The chat feature calls `${VITE_API_URL}/chat/` (defaults to `http://localhost:8000`).

## Quick start

```bash
pnpm install
pnpm dev          # http://localhost:3000 (Vite dev server, hot-reload)
```

## Scripts

| Script | Purpose |
|---|---|
| `pnpm dev` | Start the Vite dev server with hot-reload (port 3000). |
| `pnpm build` | Production build. |
| `pnpm preview` | Preview the production build locally. |
| `pnpm test` | Run Vitest unit + component tests (jsdom environment). |
| `pnpm test:e2e` | Run Playwright end-to-end tests. Auto-starts the dev server unless `APP_URL` is set. |
| `pnpm check` | Biome lint + format check (read-only). |
| `pnpm format` | Auto-format with Biome. |
| `pnpm typecheck` | TypeScript typecheck (`tsc --noEmit`). |
| `pnpm knip` | Detect dead code and unused files. |
| `pnpm lhci` | Run a local Lighthouse CI audit. |
| `pnpm react-compiler:healthcheck` | Verify React Compiler health. |

## Project structure

```
src/
  routes/         ← TanStack Router file-based routes (page entry points only)
  widgets/        ← composite blocks combining entities + features (e.g. graph-viewer)
  features/       ← self-contained feature slices (e.g. chat/)
  entities/       ← domain models + their UI
  shared/         ← cross-cutting utilities, UI primitives, API client, config
  paraglide/      ← GENERATED — do not edit manually; regenerated on dev/build
  test/           ← shared test utilities (e.g. fixtures, mothers)
```

## Architecture — Feature-Sliced Design (FSD)

Code is organised into vertical slices (`features/`, `entities/`, `widgets/`) plus a horizontal `shared/` layer. Each slice owns its `ui/`, `model/`, and `api/` sub-directories. Slices may import from `shared/` but **not from sibling features**.

Import rules are enforced at lint time by Biome's `noRestrictedImports` rule (see `biome.json`), not just by convention. The legacy `@/*` path alias is banned; the modern `#/*` subpath import (declared in `package.json` `imports` and `tsconfig.json`) is used everywhere.

## i18n (Paraglide)

- Message keys live in `messages/en.json` and `messages/es.json` (one file per locale).
- `src/paraglide/` is **auto-generated** — never edit it directly.
- Run `pnpm dev` or `pnpm build` to regenerate the Paraglide outputs after adding or changing message keys.
- URL routing is localised through the Paraglide Vite plugin (locale encoded in the URL, strategy `["url", "baseLocale"]`).

## Styling

Tailwind CSS v4 (via `@tailwindcss/vite`) and the [HeroUI](https://www.heroui.com/) component library (`@heroui/react`). Styling is done with Tailwind utility classes alongside HeroUI's variant props. There is no shadcn/ui — `README` files from the default `create-tanstack-app` template referencing it have been replaced.

## Testing

- **Unit + component tests** — Vitest + Testing Library + `jest-dom` in a `jsdom` environment.
- **End-to-end tests** — Playwright (chromium-only) with axe-core accessibility checks. The Playwright config auto-starts `pnpm dev` unless `APP_URL` is set to point at an already-running server.
- **Shared fixtures** — chat message fixtures live in `src/test/mothers/chat.mother.ts`, a single source of truth used by both Vitest unit tests and Playwright e2e tests.

## Backend connection

Chat talks to the backend via the Vercel AI SDK v6 `DefaultChatTransport` pointing at `${VITE_API_URL}/chat/`. The backend emits a Vercel AI SDK-compatible SSE stream (see `../backend/api/vercel_stream.py`).

To target a non-local backend, set `VITE_API_URL` in a `.env` file (or your shell environment) before running `pnpm dev` / `pnpm build`. The variable is read and Zod-validated in `src/shared/config/env.ts`.

A typed REST client for the future `/graph` endpoints is not yet implemented — it will land in `src/shared/api/` when the graph visualisation feature starts.

## Contributing

For architecture conventions, binding constraints, and coding rules, see [`CLAUDE.md`](./CLAUDE.md). For design decisions that govern the wider project (pipeline, graph, backend), see the [`docs/decisions/`](../docs/decisions/) ADRs.