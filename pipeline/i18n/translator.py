"""
Spanish translation stage for the Neo4j knowledge graph.

``Translator().run()`` iterates over every embeddable label, fetches nodes whose
``name_es`` property is NULL (resumable — re-running skips already-translated nodes),
translates ``name`` and ``text`` via a local Ollama chat model, and writes the
translations back as the flat sibling columns ``name_es``/``text_es`` (schema v3.1,
ADR-0005 §4 — no nested ``i18n`` map).

This is a one-off enrichment stage, mirroring ``pipeline/embeddings/generator.py``:
same per-label loop, same resumable ``WHERE ... IS NULL`` fetch, same batched
``UNWIND $rows ... SET`` write.

Translation uses a **local** LLM (Ollama) rather than a paid API, keeping the same
"no external API, no per-call cost" property the project already committed to for
embeddings (ADR-0001). A translation-memory cache (``translations/es.json``) dedups
repeated source strings (many node names/text repeat verbatim across the graph) and
lets a long local-model run resume cheaply if interrupted.

Note: this stage must run *after* ``embed`` — the embed stage overwrites ``n.text``
with enriched graph-context text, and that is what gets translated and what the
retriever/frontend serve as citation source. Re-running ``embed`` after ``translate``
makes ``text_es`` stale; re-run ``translate`` again in that case.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from tqdm import tqdm

from pipeline.constants import EMBEDDABLE_LABELS
from pipeline.graph import client

load_dotenv()

logger = logging.getLogger(__name__)

_WRITE_BATCH = 200
_CACHE_SAVE_EVERY = 50  # flush the translation-memory cache every N new entries

_CACHE_PATH = Path(__file__).parent / "translations" / "es.json"

_SYSTEM_PROMPT = (
    "You are a professional English-to-Spanish translator for Warhammer: The Old "
    "World, a tabletop miniature wargame. Translate the given text into natural, "
    "European Spanish, including proper nouns (unit names, special rule names, "
    "spell names, item names) — translate them too, don't leave them in English. "
    "Preserve all formatting exactly: line breaks, punctuation, numbers, and any "
    "markdown-like structure. Return ONLY the translated text, with no preamble, "
    "no quotes, and no explanation."
)


class Translator:
    """Orchestrates Spanish translation for all embeddable graph labels."""

    def __init__(self, translate_fn: Callable[[str], str] | None = None) -> None:
        # Injected for tests; when None, run() lazily builds an Ollama-backed
        # translator so importing this module never requires langchain_ollama.
        self._translate_fn = translate_fn

    def run(self) -> None:
        driver = client.get_driver()
        translate = self._translate_fn or self._build_translator()
        cache = self._load_cache()

        for label in EMBEDDABLE_LABELS:
            self._translate_label(driver, translate, cache, label)

        self._save_cache(cache)
        logger.info("Translation stage complete")

    # ------------------------------------------------------------------
    # Ollama-backed translation callable
    # ------------------------------------------------------------------

    def _build_translator(self) -> Callable[[str], str]:
        model_name = os.environ.get("TRANSLATE_MODEL") or os.environ.get("LLM_MODEL")
        if not model_name:
            raise RuntimeError(
                "No translation model configured. Set TRANSLATE_MODEL (or LLM_MODEL) "
                "to an Ollama model tag, e.g. TRANSLATE_MODEL=llama3.1"
            )
        base_url = os.environ.get("LOCAL_LLM_BASE_URL")

        logger.info("Loading Ollama translation model: %s (base_url=%s)", model_name, base_url)
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_ollama import ChatOllama

        kwargs: dict[str, object] = {"model": model_name, "temperature": 0}
        if base_url:
            kwargs["base_url"] = base_url
        llm = ChatOllama(**kwargs)

        def _translate(text: str) -> str:
            messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=text)]
            response = llm.invoke(messages)
            return str(response.content).strip()

        return _translate

    # ------------------------------------------------------------------
    # Per-label translation
    # ------------------------------------------------------------------

    def _translate_label(
        self,
        driver,
        translate: Callable[[str], str],
        cache: dict[str, str],
        label: str,
    ) -> None:
        nodes = self._fetch_untranslated(driver, label)
        if not nodes:
            logger.info("%s: all nodes already translated, skipping", label)
            return

        logger.info("%s: translating %d nodes", label, len(nodes))
        rows: list[dict[str, str]] = []
        new_cache_entries = 0

        for node in tqdm(nodes, desc=f"Translating {label}", unit="node"):
            name_es = self._translate_cached(translate, cache, node["name"])
            row: dict[str, str] = {"id": node["id"], "name_es": name_es}

            text = node.get("text")
            if text:
                row["text_es"] = self._translate_cached(translate, cache, text)

            rows.append(row)
            new_cache_entries += 1
            if new_cache_entries % _CACHE_SAVE_EVERY == 0:
                self._save_cache(cache)

        total_written = 0
        for start in range(0, len(rows), _WRITE_BATCH):
            batch = rows[start : start + _WRITE_BATCH]
            self._write_translations(driver, label, batch)
            total_written += len(batch)

        logger.info("%s: wrote %d translations", label, total_written)

    def _translate_cached(
        self, translate: Callable[[str], str], cache: dict[str, str], source: str
    ) -> str:
        if source in cache:
            return cache[source]
        translated = translate(source)
        cache[source] = translated
        return translated

    def _fetch_untranslated(self, driver, label: str) -> list[dict]:
        query = f"""
            MATCH (n:{label})
            WHERE n.name_es IS NULL AND n.name IS NOT NULL
            RETURN n.id AS id, n.name AS name, n.text AS text
        """
        with driver.session() as session:
            result = session.run(query)
            return [{"id": rec["id"], "name": rec["name"], "text": rec["text"]} for rec in result]

    def _write_translations(self, driver, label: str, rows: list[dict[str, str]]) -> None:
        # Rows may or may not have a "text_es" key (omitted when source text was
        # null/empty) — split so we never write an empty-string translation.
        with_text = [r for r in rows if "text_es" in r]
        without_text = [
            {"id": r["id"], "name_es": r["name_es"]} for r in rows if "text_es" not in r
        ]

        if with_text:
            query = f"""
                UNWIND $rows AS row
                MATCH (n:{label} {{id: row.id}})
                SET n.name_es = row.name_es, n.text_es = row.text_es
            """
            with driver.session() as session:
                session.execute_write(lambda tx, b=with_text: tx.run(query, rows=b))

        if without_text:
            query = f"""
                UNWIND $rows AS row
                MATCH (n:{label} {{id: row.id}})
                SET n.name_es = row.name_es
            """
            with driver.session() as session:
                session.execute_write(lambda tx, b=without_text: tx.run(query, rows=b))

    # ------------------------------------------------------------------
    # Translation-memory cache
    # ------------------------------------------------------------------

    def _load_cache(self) -> dict[str, str]:
        if not _CACHE_PATH.exists():
            return {}
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("%s is corrupt JSON, starting with an empty cache", _CACHE_PATH)
            return {}

    def _save_cache(self, cache: dict[str, str]) -> None:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
