# CLAUDE.md — tests/

Scoped context for the test suite.
For project overview and coding conventions, see [`../CLAUDE.md`](../CLAUDE.md).

---

## Layout

```
tests/
  unit/           ← isolated unit tests (no Neo4j, no network)
  integration/    ← tests that require a running Neo4j instance
  evaluation/     ← RAG quality evaluation (golden query set)
```

## Running tests

```bash
make test         # runs full pytest suite from project root
pytest tests/unit # unit tests only (no external deps)
```

Frontend tests are separate:
```bash
cd frontend && pnpm test       # Vitest
cd frontend && pnpm test:e2e   # Playwright (needs dev server running)
```

---

## Evaluation suite

`evaluation/test_queries.json` is the golden set of expected RAG behaviour — the authoritative reference for what the assistant should answer and how.
Run `tests/evaluation/evaluate.py` to score the RAG pipeline against it.
Do not add RAG-relevant tests elsewhere; keep the golden set here.

---

## Rules

- Unit tests must not touch Neo4j or the network. Mock at the boundary if needed.
- Integration tests require a live Neo4j instance; mark them with `@pytest.mark.integration` so CI can skip them without a database.
- Test descriptions (function names, docstrings) in English, same as all project text.
