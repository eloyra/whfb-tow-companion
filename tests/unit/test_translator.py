"""Unit tests for the Spanish translation stage.

Tests use a fake Neo4j driver and an injected ``translate_fn`` so no real Neo4j
instance or Ollama model is required.
"""

from __future__ import annotations

from typing import Any

from pipeline.i18n.translator import _WRITE_BATCH, Translator


class FakeRecord:
    """Minimal Record-like object, mirrors tests/unit/test_retriever.py."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]


class FakeResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = [FakeRecord(r) for r in records]

    def __iter__(self):
        return iter(self._records)


class FakeSession:
    """Routes reads to the canned rows and logs writes on the owning driver."""

    def __init__(self, driver: "FakeDriver") -> None:
        self._driver = driver

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def run(self, query: str, **params: Any) -> FakeResult:
        if "rows" in params:
            self._driver.write_log.append((query, params["rows"]))
            return FakeResult([])
        self._driver.read_queries.append(query)
        return FakeResult(self._driver.read_rows)

    def execute_write(self, fn):
        return fn(self)


class FakeDriver:
    def __init__(self, read_rows: list[dict[str, Any]]) -> None:
        self.read_rows = read_rows
        self.read_queries: list[str] = []
        self.write_log: list[tuple[str, list[dict[str, Any]]]] = []

    def session(self) -> FakeSession:
        return FakeSession(self)


def _translate_fn_factory(calls: list[str]):
    """A fake translate_fn that records every source string it's asked to translate."""

    def _translate(text: str) -> str:
        calls.append(text)
        return f"ES:{text}"

    return _translate


def test_fetch_untranslated_filters_missing_name_es() -> None:
    driver = FakeDriver([{"id": "fear", "name": "Fear", "text": "Causes Fear."}])
    translator = Translator()

    nodes = translator._fetch_untranslated(driver, "SpecialRule")

    assert nodes == [{"id": "fear", "name": "Fear", "text": "Causes Fear."}]
    assert "n.name_es IS NULL" in driver.read_queries[0]
    assert "n.name IS NOT NULL" in driver.read_queries[0]


def test_translate_label_writes_name_es_and_text_es() -> None:
    driver = FakeDriver([{"id": "fear", "name": "Fear", "text": "Causes Fear."}])
    calls: list[str] = []
    translator = Translator()

    translator._translate_label(driver, _translate_fn_factory(calls), {}, "SpecialRule")

    assert len(driver.write_log) == 1
    query, rows = driver.write_log[0]
    assert "name_es" in query and "text_es" in query
    assert rows == [{"id": "fear", "name_es": "ES:Fear", "text_es": "ES:Causes Fear."}]


def test_translate_label_skips_text_es_when_text_is_null() -> None:
    driver = FakeDriver([{"id": "abyssal-terror", "name": "Abyssal Terror", "text": None}])
    calls: list[str] = []
    translator = Translator()

    translator._translate_label(driver, _translate_fn_factory(calls), {}, "Unit")

    query, rows = driver.write_log[0]
    assert "text_es" not in query
    assert rows == [{"id": "abyssal-terror", "name_es": "ES:Abyssal Terror"}]


def test_translate_label_skips_already_translated_nodes() -> None:
    """Resumability is enforced Cypher-side (WHERE n.name_es IS NULL); when the
    fetch returns nothing there is no translation work and no write at all."""
    driver = FakeDriver([])
    calls: list[str] = []
    translator = Translator()

    translator._translate_label(driver, _translate_fn_factory(calls), {}, "SpecialRule")

    assert driver.write_log == []
    assert calls == []


def test_translation_memory_cache_dedups_repeated_source_strings() -> None:
    driver = FakeDriver(
        [
            {"id": "fear", "name": "Fear", "text": "Fear"},
            {"id": "terror", "name": "Fear", "text": "Fear"},
        ]
    )
    calls: list[str] = []
    cache: dict[str, str] = {}
    translator = Translator()

    translator._translate_label(driver, _translate_fn_factory(calls), cache, "SpecialRule")

    # "Fear" is the source for both name and text on both nodes — translated once.
    assert calls == ["Fear"]
    assert cache == {"Fear": "ES:Fear"}
    _, rows = driver.write_log[0]
    assert rows[0]["name_es"] == "ES:Fear"
    assert rows[1]["name_es"] == "ES:Fear"


def test_translate_label_writes_incrementally_not_only_at_the_end() -> None:
    """A label larger than _WRITE_BATCH must flush to Neo4j as it goes, so an
    interrupted run (or a graph rebuild between labels) doesn't lose already
    -translated nodes' persisted state — only the cache file would otherwise
    survive a kill mid-label."""
    node_count = _WRITE_BATCH + 5
    driver = FakeDriver(
        [{"id": f"n{i}", "name": f"Name{i}", "text": None} for i in range(node_count)]
    )
    calls: list[str] = []
    translator = Translator()

    translator._translate_label(driver, _translate_fn_factory(calls), {}, "SpecialRule")

    # One full batch of _WRITE_BATCH plus a final flush of the remaining 5 —
    # not a single write after collecting all node_count rows.
    assert len(driver.write_log) == 2
    first_batch_rows = driver.write_log[0][1]
    second_batch_rows = driver.write_log[1][1]
    assert len(first_batch_rows) == _WRITE_BATCH
    assert len(second_batch_rows) == 5
    assert sum(len(rows) for _, rows in driver.write_log) == node_count


def test_write_translations_splits_batches_with_and_without_text() -> None:
    driver = FakeDriver([])
    translator = Translator()
    rows = [
        {"id": "a", "name_es": "A"},
        {"id": "b", "name_es": "B", "text_es": "B text"},
    ]

    translator._write_translations(driver, "SpecialRule", rows)

    assert len(driver.write_log) == 2
    queries = [q for q, _ in driver.write_log]
    assert any("text_es" in q for q in queries)
    assert any("text_es" not in q for q in queries)
