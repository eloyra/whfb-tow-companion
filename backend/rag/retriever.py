"""Semantic retrieval against the Neo4j vector indexes.

The retriever embeds the user query with the same SentenceTransformer model used at
ingestion time and runs label-scoped approximate-nearest-neighbour (ANN) searches
across all embeddable node labels. Results are merged globally by score and
deduplicated by node id.

ADR-0001 mandates ``neo4j-graphrag``'s ``VectorCypherRetriever`` for retrieval.
This implementation uses raw ``db.index.vector.queryNodes`` calls instead: they
expose the same HNSW ANN behaviour with less wrapper overhead, which keeps the
baseline small and easy to debug. A future refactor can wrap this in
``VectorCypherRetriever`` without changing the public ``retrieve()`` contract.

``strategy`` selects the ranking source: ``"vector"`` (default) is pure ANN;
``"hybrid"`` additionally queries the single multi-label full-text index and
fuses both ranked lists via Reciprocal Rank Fusion (see ADR-0008). The
``lexical_fallback`` exact-name-match boost is an independent, optional knob
orthogonal to ``strategy`` — see ``backend/api/dependencies.py::get_rag_pipeline``
for how ``RAG_MODE`` maps to both.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import neo4j
import numpy as np

from pipeline.constants import EMBEDDABLE_LABELS
from pipeline.graph.ddl import FULLTEXT_INDEX_NAME

logger = logging.getLogger(__name__)

# Score assigned to a lexical (exact-name) match, guaranteeing it outranks
# pure-vector results. Neo4j's cosine-similarity vector index returns scores
# in [0, 1], so this always sorts first.
_LEXICAL_MATCH_SCORE = 1.0

# Reciprocal Rank Fusion smoothing constant. 60 is the standard value from the
# original RRF paper (Cormack et al., 2009) and is not query-tuned; it damps
# the influence of rank-1 items just enough that a node appearing in both
# lists (even at a middling rank in each) can outscore a node ranked #1 in
# only one list.
RRF_K = 60

# Lucene special characters that must be backslash-escaped in a full-text
# query string, or Neo4j's query-parser throws a syntax error. Order matters:
# backslash itself must be escaped first so later escapes aren't re-escaped.
_LUCENE_SPECIAL_CHARS = '\\+-&|!(){}[]^"~*?:/'

# Matches a trailing parenthetical placeholder, e.g. " (X)" in "Fly (X)".
_PARENTHETICAL_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")

# Minimal suffix-stripping "stemmer", applied word-by-word so a query can use
# a different inflection than the node name (e.g. "disrupts units" vs.
# "Disrupted Units", "named character" vs. "Named Characters"). Order matters:
# longer/more specific suffixes are tried first.
_STEM_SUFFIX_RULES: list[tuple[str, str]] = [
    ("ies", "y"),
    ("ed", ""),
    ("ing", ""),
    ("es", ""),
    ("s", ""),
]
_MIN_STEM_LEN = 3


def _stem(word: str) -> str:
    for suffix, replacement in _STEM_SUFFIX_RULES:
        if word.endswith(suffix) and len(word) - len(suffix) + len(replacement) >= _MIN_STEM_LEN:
            return word[: -len(suffix)] + replacement
    return word


def _lucene_escape(query: str) -> str:
    """Escape Lucene special characters in a raw query string.

    Golden-set queries routinely contain ``?`` and ``:`` (e.g. "What is the
    Stubborn rule?"); passed unescaped to ``db.index.fulltext.queryNodes``
    these are parsed as Lucene operators (wildcard, field-selector) and raise
    a syntax error instead of matching literally.
    """
    return "".join(f"\\{ch}" if ch in _LUCENE_SPECIAL_CHARS else ch for ch in query)


def _label_to_snake(label: str) -> str:
    """Convert CamelCase label to snake_case for vector-index naming."""
    s = re.sub(r"([A-Z])", r"_\1", label).lower().lstrip("_")
    return s


class GraphRAGRetriever:
    """Embed a query and retrieve the most relevant nodes from Neo4j."""

    def __init__(
        self,
        driver: neo4j.Driver,
        embedder: Any,
        *,
        top_k: int = 8,
        per_label_k: int | None = None,
        strategy: str = "vector",
        lexical_fallback: bool = False,
    ) -> None:
        self.driver = driver
        self.embedder = embedder
        self.top_k = top_k
        # Fetch a wider per-label candidate pool than top_k before the global
        # merge/cut: relevant nodes often rank outside the top-k within their
        # own label (e.g. a short CoreRule definition losing raw cosine score
        # to longer, more verbose FAQ/Lore text) but still belong in the
        # global top_k once all labels are pooled together.
        self.per_label_k = per_label_k or max(top_k * 3, 20)
        if strategy not in ("vector", "hybrid"):
            raise ValueError(
                f"Unsupported retrieval strategy '{strategy}'. Use 'vector' or 'hybrid'."
            )
        self.strategy = strategy
        self.lexical_fallback = lexical_fallback
        self._name_index: list[tuple[str, str, str, str]] | None = None

    def retrieve(self, query: str) -> list[dict[str, Any]]:
        """Return the top-k most relevant nodes for ``query``.

        Each result is a dict with keys: ``id``, ``label``, ``name``, ``text``,
        ``url``, ``score``.
        """
        vector = self._embed(query)
        all_results: list[dict[str, Any]] = []

        for label in EMBEDDABLE_LABELS:
            try:
                label_results = self._query_label(label, vector, self.per_label_k)
            except Exception as exc:  # noqa: BLE001 — log and continue with other labels
                logger.warning("Vector query failed for %s: %s", label, exc)
                continue
            all_results.extend(label_results)

        # Deduplicate by id, keeping the highest score.
        by_id: dict[str, dict[str, Any]] = {}
        for result in all_results:
            rid = result["id"]
            if rid not in by_id or result["score"] > by_id[rid]["score"]:
                by_id[rid] = result

        if self.strategy == "hybrid":
            vector_ranked = sorted(by_id.values(), key=lambda r: r["score"], reverse=True)
            try:
                fulltext_ranked = self._query_fulltext(query, self.per_label_k)
            except Exception as exc:  # noqa: BLE001 — degrade to vector-only on failure
                logger.warning("Full-text query failed: %s", exc)
                fulltext_ranked = []
            by_id = {r["id"]: r for r in self._fuse_rrf(vector_ranked, fulltext_ranked)}

        # Lexical fallback: a node whose exact name appears as a whole phrase
        # in the query is very likely relevant even when its raw cosine score
        # is mediocre (short/common node names like "Fly" or rulebook-prose
        # register mismatches lose to more verbose competing text). Force
        # these into the pool at the top score so they aren't crowded out.
        # Independent of ``strategy`` — a droppable add-on, not core behavior.
        if self.lexical_fallback:
            for match in self._lexical_matches(query):
                rid = match["id"]
                if rid not in by_id or by_id[rid]["score"] < _LEXICAL_MATCH_SCORE:
                    by_id[rid] = match

        ranked = sorted(by_id.values(), key=lambda r: r["score"], reverse=True)
        return ranked[: self.top_k]

    def _lexical_matches(self, query: str) -> list[dict[str, Any]]:
        """Return nodes whose ``name`` appears as a whole phrase in ``query``.

        Builds an in-memory (id, label, name, text, url) index once per
        retriever instance (cheap: a few thousand rows, no embeddings
        involved).

        Variable-value special rules are stored with a placeholder suffix
        (e.g. "Fly (X)", "Armour Bane (X)") that never appears verbatim in
        plain-language queries, so the trailing parenthetical is also tried
        stripped off.

        Multi-word names additionally match on a per-word stem (e.g. "What
        terrain disrupts units?" against "Disrupted Units") so the query can
        use a different inflection than the canonical rule name. Single-word
        names deliberately skip stemming and use an exact word-boundary match
        instead — stemming a short word like "Fly" would also swallow
        unrelated words like "flying"/"butterfly".
        """
        if self._name_index is None:
            self._name_index = self._fetch_name_index()

        query_lower = query.lower()
        query_words = re.findall(r"\w+", query_lower)
        query_stems = [_stem(w) for w in query_words]

        matches: list[dict[str, Any]] = []
        for node_id, label, name, text, url in self._name_index:
            if not name:
                continue
            bare_name = _PARENTHETICAL_SUFFIX_RE.sub("", name).strip()
            candidates = {name.lower(), bare_name.lower()}
            if any(candidate and self._phrase_in_query(candidate, query_lower, query_stems)
                   for candidate in candidates):
                matches.append(
                    {
                        "id": node_id,
                        "label": label,
                        "name": name,
                        "text": text or name,
                        "url": url,
                        "score": _LEXICAL_MATCH_SCORE,
                    }
                )
        return matches

    @staticmethod
    def _phrase_in_query(candidate: str, query_lower: str, query_stems: list[str]) -> bool:
        """Return whether ``candidate`` (a node name, lowercased) matches ``query``.

        Single-word candidates require an exact word-boundary substring match.
        Multi-word candidates additionally accept a per-word-stem match, so
        "Disrupted Units" matches a query containing "disrupts units".
        """
        words = candidate.split()
        if re.search(r"\b" + re.escape(candidate) + r"\b", query_lower):
            return True
        if len(words) < 2:
            return False
        candidate_stems = [_stem(w) for w in words]
        n = len(candidate_stems)
        return any(
            query_stems[i : i + n] == candidate_stems for i in range(len(query_stems) - n + 1)
        )

    def _fetch_name_index(self) -> list[tuple[str, str, str, str, str]]:
        """Fetch (id, label, name, text, url) for every embeddable node, once."""
        rows: list[tuple[str, str, str, str, str]] = []
        for label in EMBEDDABLE_LABELS:
            try:
                with self.driver.session() as session:
                    result = session.run(
                        f"MATCH (n:{label}) WHERE n.name IS NOT NULL "
                        "RETURN n.id AS id, n.name AS name, n.text AS text, n.url AS url",
                        label=label,
                    )
                    for record in result:
                        rows.append(
                            (record["id"], label, record["name"], record["text"], record["url"])
                        )
            except Exception as exc:  # noqa: BLE001 — log and continue with other labels
                logger.warning("Name-index fetch failed for %s: %s", label, exc)
                continue
        return rows

    def _embed(self, query: str) -> list[float]:
        """Encode ``query`` into the embedding vector used by Neo4j."""
        vector = self.embedder.encode(query, convert_to_numpy=True, normalize_embeddings=False)
        if isinstance(vector, np.ndarray):
            vector = vector.tolist()
        # encode() may return a 2-D array if given a list; a single string should be 1-D.
        if isinstance(vector, list) and vector and isinstance(vector[0], list):
            vector = vector[0]
        return vector  # type: ignore[return-value]

    def _query_label(
        self,
        label: str,
        vector: list[float],
        k: int,
    ) -> list[dict[str, Any]]:
        """Run vector ANN for a single label."""
        index_name = f"{_label_to_snake(label)}_embedding_idx"
        cypher = """
            CALL db.index.vector.queryNodes($index_name, $k, $vector)
            YIELD node, score
            RETURN node.id AS id,
                   $label AS label,
                   node.name AS name,
                   coalesce(node.text, node.name, '') AS text,
                   node.url AS url,
                   score
            ORDER BY score DESC
        """
        with self.driver.session() as session:
            result = session.run(
                cypher,
                index_name=index_name,
                k=k,
                vector=vector,
                label=label,
            )
            rows = []
            for record in result:
                row = dict(record)
                # Cypher coalesce handles nulls; this also guards against missing props.
                row["text"] = row.get("text") or row.get("name") or ""
                rows.append(row)
            return rows

    def _query_fulltext(self, query: str, k: int) -> list[dict[str, Any]]:
        """Run BM25 full-text search over the single multi-label index.

        Unlike vector search, one full-text index spans every embeddable
        label, so this yields one already-globally-ranked list — no per-label
        merge step needed.
        """
        cypher = """
            CALL db.index.fulltext.queryNodes($index_name, $search_text, {limit: $k})
            YIELD node, score
            RETURN node.id AS id,
                   labels(node)[0] AS label,
                   node.name AS name,
                   coalesce(node.text, node.name, '') AS text,
                   node.url AS url,
                   score
            ORDER BY score DESC
        """
        with self.driver.session() as session:
            # Note: neo4j's Session.run(query, ...) reserves the name "query"
            # for its own first positional parameter, so the Cypher parameter
            # must be named differently to avoid a keyword collision.
            result = session.run(
                cypher,
                index_name=FULLTEXT_INDEX_NAME,
                search_text=_lucene_escape(query),
                k=k,
            )
            rows = []
            for record in result:
                row = dict(record)
                row["text"] = row.get("text") or row.get("name") or ""
                rows.append(row)
            return rows

    @staticmethod
    def _fuse_rrf(
        vector_ranked: list[dict[str, Any]],
        fulltext_ranked: list[dict[str, Any]],
        k_const: int = RRF_K,
    ) -> list[dict[str, Any]]:
        """Fuse two independently-ranked result lists via Reciprocal Rank Fusion.

        ``score = sum(1 / (k_const + rank))`` over every list a node appears
        in, with 1-based rank. Each input list must already be sorted best
        first (as both ``_query_label``/vector-merge and ``_query_fulltext``
        return). The fused ``score`` replaces each node's original
        vector-cosine or BM25 score — the two are on incomparable scales, so
        only the fused rank-based score is meaningful downstream.
        """
        fused: dict[str, dict[str, Any]] = {}
        rrf_scores: dict[str, float] = {}

        for ranked_list in (vector_ranked, fulltext_ranked):
            for rank, row in enumerate(ranked_list, start=1):
                rid = row["id"]
                rrf_scores[rid] = rrf_scores.get(rid, 0.0) + 1.0 / (k_const + rank)
                if rid not in fused:
                    fused[rid] = row

        for rid, node in fused.items():
            node["score"] = rrf_scores[rid]

        return sorted(fused.values(), key=lambda r: r["score"], reverse=True)
