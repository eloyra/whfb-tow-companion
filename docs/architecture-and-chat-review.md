# Architecture & Chat Implementation Review

> Review of project architecture and chat implementation against industry best practices and standards. Findings grouped by layer with severity tags: **[CRITICAL]** (must fix before public traffic), **[HIGH]** (industry-standard gap), **[MEDIUM]** (drift / debt), **[LOW]** (polish).

---

## 1. Top-level / monorepo

### Strengths
- Clean folder-monorepo: `pipeline/`, `backend/`, `frontend/`, `data/`, `docs/`, `tests/`, `notebooks/`. Concerns separated cleanly.
- 5 binding ADRs (`docs/decisions/`) plus authoritative schema (`docs/schema/knowledge_graph_schema.md` v3.0). Doc discipline rare in academic projects.
- Scoped `CLAUDE.md` per subtree. Progressive disclosure done right.

### Issues
- **[HIGH] No CI** — no `.github/workflows/`, no pre-commit. Lint/test only enforced manually via `make lint` / `make test`. Industry standard: PR gates on lint + typecheck + tests for both Python and Node.
- **[HIGH] No application Dockerfiles** — `docker/docker-compose.yml` covers Neo4j only. No reproducible backend or frontend container, no full-stack compose for new contributors. TFM defense reproducibility risk.
- **[MEDIUM] `pyproject.toml` drift**:
  - Line 56 declares `packages = ["pipeline", "backend", "frontend"]` — `frontend/` has no Python.
  - Line 60 `target-version = "py311"` contradicts line 10 `requires-python = ">=3.12"`.
  - Line 35 `streamlit>=1.35.0` listed as runtime dep — frontend pivoted to TanStack Start; Streamlit unused.
- **[MEDIUM] `Makefile:51`** still points `make ui` at `streamlit run frontend/app.py`. Stale.
- **[MEDIUM] Top-level CLAUDE.md status checklist** marks `pipeline/embeddings/`, `backend/rag/`, `frontend/` as `[ ]` despite all three existing on disk. Drift between docs and code.
- **[LOW] No `.editorconfig`**, no `CHANGELOG.md`, no git tags, `docs/diagrams/` empty.

---

## 2. Backend architecture

### Strengths
- LangGraph `create_agent` + `stream_mode="messages"` is current industry-standard agentic pattern. Pluggable retriever via tools.
- Pydantic schemas at API boundary (`backend/api/routes/chat.py:20-38`).
- LangSmith tracing wired conditionally with env tagging (`backend/api/main.py:10-12`).
- DI for LLM (`Depends(get_llm)`) lets tests override cleanly. Test suite (`tests/unit/test_chat_stream.py`) demonstrates this with `app.dependency_overrides`.
- SSE protocol-compliance fix recently landed: `data-sources` discriminator instead of bare `data` (matches Vercel AI SDK v6 Zod union).

### Issues

#### 2.1 LLM abstraction
- **[HIGH] Two parallel LLM abstractions**:
  - `backend/llm/client.py` — `Protocol`-based, reads `LLM_PROVIDER` (openai/anthropic/local). Zero importers. Dead code per migration plan (`docs/plans/backend-langgraph-migration.md:286`).
  - `backend/api/dependencies.py:get_llm` — actual seam, returns LangChain `BaseChatModel`. Only handles `ollama` and `openai`.
- **[HIGH] `LLM_PROVIDER=anthropic` documented in `.env.example` but raises `ValueError`** at runtime (`dependencies.py:27`). Provider list is a lie.
- **[MEDIUM] Default provider mismatch**: `dependencies.py:13` defaults to `ollama`; `.env.example` says `openai`. New contributors get confused.
- **Recommendation**: delete `backend/llm/`, add Anthropic branch to `get_llm` (`langchain-anthropic` companion of the already-present `anthropic>=0.30.0`), or document its absence.

#### 2.2 Chat route (`backend/api/routes/chat.py`)
- **[HIGH] No abort/cancellation handling.** When client disconnects mid-stream, `agent.astream()` keeps running and burning LLM tokens. Standard fix: wrap in `asyncio.CancelledError` handler, or use `request.is_disconnected()`.
- **[HIGH] Message history flattening loses tool-call structure.** Lines 46-51 only handle `user`/`assistant` roles and concatenate text parts; tool messages and assistant tool-call payloads from prior turns are dropped. Multi-turn tool conversations will degrade — agent re-decides every turn instead of remembering it just called a tool.
- **[MEDIUM] No request validation beyond Pydantic.** No max message count, no max content length, no rate limit. Trivially DoS-able with a large-message body.
- **[MEDIUM] Agent recreated every request** (line 53). Fine for now, but caching by `(provider, model)` would save startup cost once retriever is real.
- **[LOW] `ChatRequest` has no `id` / `chat_id`** — no concept of session/conversation. Acceptable for stateless thesis demo; flag for future.
- **[LOW] No structured logging.** No request ID, no span IDs, no token counts. LangSmith covers some of this; add `structlog` or stdlib JSON logging for HTTP layer.

#### 2.3 SSE (`backend/api/vercel_stream.py`)
- **[HIGH] No keepalive / heartbeat.** Long idle gaps (slow tool calls) can be killed by intermediate proxies. Standard pattern: `: ping\n\n` comment frame every ~15s.
- **[HIGH] Bare `except Exception` swallows traceback** (line 48). The error event leaks `str(e)` to client (which can include sensitive paths) and there is no server-side log of the stack. Split: log stack server-side, send opaque error id to client.
- **[MEDIUM] `msg.content` only handled when `isinstance(msg.content, str)`** (line 24). LangChain message content can be a list of content blocks (e.g. when using Anthropic with tool use). When that happens deltas silently drop.
- **[MEDIUM] No `tool-input-start/delta` events** — frontend cannot show "calling tool…" placeholder. Migration plan acknowledges this is deferred.
- **[LOW] `msg_id` stable across whole stream** even if agent emits multiple `AIMessage` turns (after a tool call the agent typically emits a second AI message). Vercel SDK expects a new `text-start`/`text-end` pair per turn or per assistant message — verify against agent traces with tool calls.

#### 2.4 RAG core
- **[CRITICAL for thesis] RAG is a mock.** `backend/rag/tools.py:15-24` returns hardcoded 2-node JSON. `backend/rag/{pipeline,retriever,graph_traversal}.py` and `prompts/templates.py` are 1-line `# TODO`. The whole "GraphRAG" thesis claim rests on code that does not exist yet. The pipeline writes embeddings to Neo4j, but no retriever reads them.
- **Recommendation**: implement Neo4j vector + graph-traversal retriever as next priority. Plan exists in `docs/plans/graph-and-embeddings-execution.md`.

#### 2.5 API surface
- **[HIGH] `GET /graph/nodes`, `GET /graph/subgraph/{id}` raise `NotImplementedError`** (`backend/api/routes/graph.py`). Either implement, or remove from router until ready (returning 500 silently breaks any client that probes).
- **[HIGH] `/health` is trivial** — returns `{"status": "ok"}` regardless of Neo4j or LLM availability. Standard liveness/readiness split: `/healthz` (process up) + `/readyz` (deps reachable).
- **[HIGH] CORS `allow_origins=["*"]`** with `# restrict in production` TODO. Acceptable for local dev; must be env-gated before any deployment.
- **[MEDIUM] No API versioning prefix** (`/v1/chat`). Frontend / SDK consumers cannot evolve safely. Cheap to add now, expensive after first external user.
- **[LOW] No OpenAPI docs customisation.** `app.openapi()` is exposed for free — exploit it for type generation (see §6).

---

## 3. Frontend architecture

### Strengths
- **FSD enforced via Biome** — `frontend/biome.json:48-130` blocks shared→entities, shared→features, entities→features, features→widgets/pages/app. Cleanest FSD enforcement seen in any project of this scope. Beats lint-rule conventions.
- TypeScript strict + `noUnusedLocals` + `noUnusedParameters` + `noFallthroughCasesInSwitch` + `noUncheckedSideEffectImports` (`tsconfig.json:24-28`). Strong defaults.
- Modern subpath imports `#/*` (replaces legacy `@/*`); explicitly enforced via `noRestrictedImports` (`biome.json:39-46`).
- Vitest + Playwright + axe-core a11y tests — proper test pyramid.
- TanStack Start with SSR + SPA dual mode (`vite.config.ts:19-23`).
- `next-themes` with `suppressHydrationWarning`, `ThemeProvider` at root. Done right.
- Paraglide i18n with `strategy: ["url", "baseLocale"]` — locale in URL, free SEO. Two locales (en/es) in sync (`messages/en.json`, `messages/es.json`).
- Zod-validated env (`src/shared/config/env.ts:3-9`) — bulletproof config boundary.
- Test mother pattern (`src/test/mothers/chat.mother.ts`) — domain-specific factories shared between Vitest and Playwright via `sseStream()`. Excellent.
- `ChatInterface` accessibility: `role="log"`, `aria-live="polite"`, `aria-label` on input + buttons, axe-core CI-friendly tests.
- `useChat` from `@ai-sdk/react` v3 — current industry-standard chat hook.

### Issues

#### 3.1 FSD compliance
- **[MEDIUM] `src/entities/unit_example/`** is empty scaffolding (`api/`, `model/`, `ui/` all empty). Placeholder. Either populate (Unit, SpecialRule, Spell, MagicItem entities mirroring graph schema) or delete to avoid confusion.
- **[LOW] No `widgets/` or `pages/` layer** — fine for thin chat-only app, but the moment graph visualisation arrives a `widgets/graph-viewer/` slice will be needed.

#### 3.2 ChatInterface (`src/features/chat/ui/ChatInterface.tsx`)
- **[HIGH] No abort on unmount.** `useChat` returns `stop`, but it isn't called in cleanup effect. If user navigates away mid-stream the request keeps streaming server-side. Add:
  ```tsx
  useEffect(() => () => stop(), [stop]);
  ```
- **[HIGH] No virtualisation for long histories.** Every message rendered into single scroll container. After ~200 messages layout thrashes. Thesis demo: fine. Real product: `@tanstack/react-virtual`.
- **[MEDIUM] `scrollIntoView` on every `messages` change** (line 26-28) is jumpy: it interrupts user reading prior context when a new token arrives. Standard pattern: only auto-scroll when user is already near the bottom. An `isNearBottom` ref + threshold check.
- **[MEDIUM] `ReactMarkdown` with no `rehype-sanitize`** — assistant output is rendered as markdown without sanitisation. LLM can be tricked into emitting `<script>` or `javascript:` URLs. ReactMarkdown defaults filter most XSS, but adding `rehype-sanitize` is industry standard and trivial.
- **[MEDIUM] No retry-with-backoff on transport errors.** Network blips show "Retry" button, fine. But silent failures (e.g. CORS preflight 502) only surface via `console.error`.
- **[LOW] Hardcoded chat container height** `h-[calc(100vh-8rem)]` (line 51) — breaks if page chrome height changes. Use CSS grid layout instead.
- **[LOW] Empty state, error state, streaming indicator** all share message panel — could be extracted into smaller components for testability.
- **[LOW] No "copy message" button**, no message timestamps, no per-message regenerate-up-to-here — features mature chat UIs have.

#### 3.3 Routing
- **[LOW] Single route `/`**. Once graph viewer arrives, separate routes for `/chat`, `/graph/{id}`. Cheap with file-based routing.
- **[LOW] `defaultPreloadStaleTime: 0`** (`router.tsx:14`) — fine for now, but combined with `defaultPreload: "intent"` it preloads on hover and refetches every time. Set a small stale time once data routes appear.

#### 3.4 State / data
- **[LOW] TanStack Query is wired** (`shared/api/query/root-provider.tsx`) but not used. Either remove or use it for the future `/graph` endpoints.
- **[LOW] No global error boundary.** Add `<ErrorBoundary>` at root + per-route.

#### 3.5 Tooling
- **[MEDIUM] `pnpm` not pinned via `packageManager`** field in `package.json`. CI / new contributors may use a wrong major. Add `"packageManager": "pnpm@<version>"`.
- **[MEDIUM] React Compiler enabled (`babel-plugin-react-compiler`) but no health check in CI** — `pnpm react-compiler:healthcheck` exists, never run.
- **[LOW] `nitro-nightly`** as dependency (`package.json:43`). Pinning a nightly is a footgun; pin to a tagged release once stable.
- **[LOW] `@heroui/react` v3.0.3** — not a household-name UI library; combined with shadcn/ui mention in `frontend/CLAUDE.md` (line 18) suggests project pivoted. Pick one and document.

---

## 4. Streaming protocol contract

The biggest cross-cutting risk:

- **[HIGH] No shared-type contract between backend SSE producer and frontend SSE consumer.** Recent `data` → `data-sources` bug (`docs/plans/backend-langgraph-fixes.md`) is direct symptom: backend emits one shape, frontend's Zod union rejects it, no compile-time guard catches it.
- The Vercel AI SDK v6 protocol shape is owned by `ai` package's Zod schema (`UIMessagePart` discriminated union). Anything backend emits must match that union — but the backend has no awareness.
- **Recommendation (cheap)**: add Vitest-level contract test that consumes a fixture SSE body produced by the Python backend (`tests/unit/test_chat_stream.py` already produces these) and asserts the frontend's Zod parser accepts it. Even a JSON snapshot file shared between Python and TS would catch the next divergence.
- **Recommendation (proper)**: codegen TypeScript from FastAPI's `/openapi.json` for non-streaming endpoints (`/health`, `/graph/*`). For SSE shapes, define them once in shared JSON Schema and generate both Pydantic and TS Zod from it.

---

## 5. Observability

- **[HIGH] No request ID.** No correlation between frontend error log → backend trace → LangSmith span. Add `X-Request-Id` middleware (echoes inbound or generates ULID), forward to LangSmith metadata, log in frontend `onError`.
- **[MEDIUM] No metrics.** No Prometheus, no OTEL. LangSmith handles LLM-side observability but HTTP latency, error rates, abort rates are blind.
- **[MEDIUM] Frontend has no error reporting.** `console.error` is the entirety of telemetry. Sentry is hinted at (`vite.config.ts:25` excludes `@sentry/*`) but not actually wired. Either install or remove the rollup external.

---

## 6. Testing

### Strengths
- Backend: unit + integration + evaluation directories. `test_chat_stream.py` covers SSE event ordering and tool-call data shape with `FakeChatModel` — pragmatic.
- Frontend: Vitest with `jsdom` + Testing Library + axe-core a11y + Playwright e2e. SSE intercepted via `page.route` using fixture body from `ChatMother.sseStream()` shared with unit tests.
- Backend test injects via `app.dependency_overrides` — proper FastAPI pattern.

### Issues
- **[HIGH] Evaluation harness is `# TODO`.** `tests/evaluation/evaluate.py` is one line. Golden set has only 3 queries (`test_queries.json`). For a TFM, evaluation rigour is the differentiator — needs ≥30 queries, scorer (recall@k for retrieval, LLM-judge or rubric for answers), and CI integration.
- **[MEDIUM] `tests/unit/test_retriever.py`** is `# TODO`. Will become most important test once retriever lands.
- **[MEDIUM] Frontend coverage gaps**: no test for streaming-in-progress UI (typing dots), no test for `stop` button click, no test for `regenerate` flow on success path. Existing tests good for what they cover but stop short.
- **[LOW] No load/perf tests** for chat endpoint. `locust` or `k6` script would surface no-abort issue immediately.

---

## 7. Security

- **[HIGH] CORS wildcard.** `allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]` in `backend/api/main.py:25-31`. Acceptable for local-dev only. **Must** be env-gated to known origins before any public deploy.
- **[HIGH] No auth on any endpoint.** Anyone with the URL can drive the LLM and burn the project's OpenAI/Anthropic credits. At minimum: API key header, rate limit per IP.
- **[HIGH] No rate limit.** Single curl loop can exhaust token budget. `slowapi` or `fastapi-limiter` (Redis) standard.
- **[MEDIUM] No request body size limit.** A 10MB JSON payload of `messages` will be parsed before validation kicks in. Configure Uvicorn `--limit-max-requests` and add Pydantic `Field(max_length=...)` on message text.
- **[MEDIUM] Markdown rendering on assistant output without sanitisation** — see §3.2. LLM-as-XSS-vector is a real and rising threat.
- **[MEDIUM] LangSmith key, OpenAI key, Anthropic key all read from `.env`** with no validation. If `OPENAI_API_KEY` is missing and `LLM_PROVIDER=openai`, error surfaces deep inside LangChain. Validate at startup.
- **[LOW] Error event leaks `str(e)`** to client — see §2.3.

---

## 8. Industry-standard gaps summary

| Concern | Status | Fix priority |
|---|---|---|
| CI pipeline | Missing | HIGH |
| Application Dockerfiles | Missing | HIGH |
| Auth + rate limit | Missing | HIGH (before any deploy) |
| CORS lockdown | Wildcard | HIGH (before any deploy) |
| Backend abort handling | Missing | HIGH |
| Frontend abort on unmount | Missing | HIGH |
| Real RAG retriever | Mock | CRITICAL for thesis |
| Eval harness | Stub | HIGH for thesis |
| Shared SSE/REST type contract | None | HIGH |
| Anthropic provider | Documented but unimplemented | HIGH |
| Dual LLM abstractions | Drift | MEDIUM |
| Multi-turn tool history | Lossy | HIGH |
| SSE keepalive | Missing | HIGH |
| Markdown XSS sanitisation | Missing | MEDIUM |
| Request ID / correlation | Missing | HIGH |
| Sentry / frontend errors | Hinted, not wired | MEDIUM |
| Streamlit refs in pyproject/Makefile | Stale | MEDIUM |
| `pyproject.toml` py311/py312 mismatch | Drift | LOW |
| Empty `entities/unit_example/` | Placeholder | LOW |
| `/health` no dep probes | Trivial | MEDIUM |
| API versioning `/v1/` | Missing | MEDIUM |
| OpenAPI → TS codegen | Missing | MEDIUM |

---

## 9. What this project does notably well

Items below above industry baseline:

1. **FSD enforced via Biome `noRestrictedImports`** (not just convention).
2. **ADR discipline** — 5 numbered, binding ADRs with rejected alternatives.
3. **Versioned schema doc** with explicit v2→v3 changelog.
4. **Test mother pattern shared across Vitest + Playwright** via single fixture factory.
5. **Zod env validation** at the only env-read site.
6. **Scoped `CLAUDE.md` per subtree** for progressive disclosure.
7. **LangSmith env tagging** for separating dev/staging/prod traces.
8. **Locale-in-URL via Paraglide** + canonical-English data with i18n field.

---

## 10. Recommended next actions (ordered by ROI)

1. **Implement the GraphRAG retriever** (`backend/rag/retriever.py`, `graph_traversal.py`, `pipeline.py`). Whole thesis hinges on this. Replace mock tool. Plan exists in `docs/plans/graph-and-embeddings-execution.md`.
2. **Build the evaluation harness** (`tests/evaluation/evaluate.py`) with ≥30 golden queries, recall@k scorer, LLM-judge for answer quality. CI-integrated.
3. **Delete `backend/llm/`** (dead) and add Anthropic branch to `dependencies.py:get_llm`. Or document anthropic is intentionally unavailable.
4. **Add request abort handling** server-side and `useEffect` cleanup `stop()` client-side.
5. **Add CI** (GitHub Actions): Python lint+tests, Node lint+typecheck+tests, Playwright smoke. Block merge on red.
6. **Add backend Dockerfile + extend compose** to include backend service. Reproducibility for thesis review.
7. **Add OpenAPI → TS codegen** (`openapi-typescript` or `orval`) so REST endpoints are type-checked end-to-end.
8. **Lock down CORS + add API key auth + rate limit** before any non-local deployment.
9. **Sanitise markdown** with `rehype-sanitize`.
10. **Fix multi-turn tool history flattening** in `chat.py:46-51` — preserve `ToolMessage` and tool-call metadata across turns.
11. **Clean up stale references**: `pyproject.toml` packages list, `Makefile` UI target, top-level CLAUDE.md status checklist, Streamlit dependency.
12. **Promote frontend swap and LangGraph migration to ADRs** (currently in `docs/plans/`). They are closed decisions; ADRs are where closed decisions belong.

---

## Critical files referenced

- `backend/api/main.py` — FastAPI app + CORS + health
- `backend/api/dependencies.py` — `get_llm` DI factory (the active LLM seam)
- `backend/api/routes/chat.py` — chat endpoint, agent invocation, message flattening
- `backend/api/routes/graph.py` — stub graph endpoints
- `backend/api/vercel_stream.py` — SSE adapter
- `backend/rag/tools.py` — mock retriever tool
- `backend/rag/prompts/system_prompt.py` — agent system prompt
- `backend/llm/client.py` — dead Protocol-based abstraction
- `frontend/src/features/chat/ui/ChatInterface.tsx` — chat UI
- `frontend/src/features/chat/ui/ChatInterface.test.tsx` — unit tests
- `frontend/src/test/mothers/chat.mother.ts` — shared Vitest+Playwright fixtures
- `frontend/src/shared/config/env.ts` — Zod-validated env
- `frontend/biome.json` — FSD enforcement rules
- `frontend/tests/e2e/chat.spec.ts`, `a11y.spec.ts` — Playwright suite
- `tests/unit/test_chat_stream.py` — backend SSE smoke tests
- `tests/evaluation/test_queries.json` — golden query set (3 queries — needs growth)
- `docs/plans/backend-langgraph-migration.md`, `backend-langgraph-fixes.md` — chat impl history
- `docs/decisions/ADR-0001..0005` — binding decisions
- `pyproject.toml` — Python deps + py311/py312 drift + stale Streamlit
- `Makefile:51` — stale Streamlit UI target

---

## Verification (how to sanity-check this review)

- `make lint && make test` — confirms backend test status.
- `pnpm check && pnpm typecheck && pnpm test && pnpm test:e2e` from `frontend/` — confirms frontend status.
- `curl http://localhost:8000/health` and `curl -N http://localhost:8000/chat/ -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","parts":[{"type":"text","text":"hello"}]}]}'` — confirms chat streams.
- `curl http://localhost:8000/graph/nodes` — confirms graph routes return 500 (NotImplementedError).
- `grep -rn "data-sources\|text-delta\|text-start\|text-end\|finish-step" backend/api/vercel_stream.py` — confirms SSE event vocabulary.
