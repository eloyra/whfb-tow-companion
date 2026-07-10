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

`evaluation/test_queries.json` is the 70-query golden set, expanded from `docs/validation/query-coverage-seed.md` and annotated with `expected_rules`, `expected_army`, `category`, and a judge `rubric`. `tests/evaluation/evaluate.py` runs retrieval-only (`make evaluate`) or full agent + LLM-judge (`make evaluate-full`) evaluation and writes JSON/Markdown reports to `tests/evaluation/reports/`.

`tests/evaluation/test_evaluate.py` contains pure-function unit tests for scoring, citation extraction, and dataset validation. These run in the normal pytest suite and act as the CI gate for the harness.

Do not add RAG-relevant tests elsewhere; keep the golden set and harness here.

---

## Rules

- Unit tests must not touch Neo4j or the network. Mock at the boundary if needed.
- Integration tests require a live Neo4j instance. The current integration suite gates on `pytest.mark.skipif(not _HAS_TESTCONTAINERS)` (a `testcontainers[neo4j]` import guard) rather than a registered `@pytest.mark.integration` marker — update the marker convention or align the suite with this doc when touching integration tests.
- Test descriptions (function names, docstrings) in English, same as all project text.
