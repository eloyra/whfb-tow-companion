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

`evaluation/test_queries.json` is intended as the golden set of expected RAG behaviour, but it is currently **skeletal (3 queries only)** and `tests/evaluation/evaluate.py` is a `# TODO` stub — the scoring harness is not implemented. A larger 50-query seed lives in `docs/validation/query-coverage-seed.md` but is not wired to any evaluator.

Do not add RAG-relevant tests elsewhere; keep the golden set here. When implementing the evaluator, expand `test_queries.json` from the `docs/validation/query-coverage-seed.md` catalogue.

---

## Rules

- Unit tests must not touch Neo4j or the network. Mock at the boundary if needed.
- Integration tests require a live Neo4j instance. The current integration suite gates on `pytest.mark.skipif(not _HAS_TESTCONTAINERS)` (a `testcontainers[neo4j]` import guard) rather than a registered `@pytest.mark.integration` marker — update the marker convention or align the suite with this doc when touching integration tests.
- Test descriptions (function names, docstrings) in English, same as all project text.
