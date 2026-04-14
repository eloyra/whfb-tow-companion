# ADR-0001 — Graph Database Selection

| Field       | Value                        |
|-------------|------------------------------|
| **Status**  | Accepted                     |
| **Date**    | 2026-02-20                   |
| **Deciders**| Project author               |
| **Tags**    | infrastructure, graph, vector |

---

## Context

The system requires a persistent store for the Warhammer: The Old World knowledge graph. The store must satisfy three simultaneous requirements:

1. **Native graph storage and traversal** — nodes (rules, units, special rules, abilities) and typed edges (hyperlinks, references, exceptions, army membership).
2. **Native vector / embedding search** — each node carries a text embedding; queries must find the nearest neighbours and then extend outward via graph traversal in a single coherent operation (the GraphRAG pattern).
3. **Python ecosystem integration** — must work with LangChain / LangGraph and support a straightforward ingestion pipeline from a BeautifulSoup scraper.

Additional constraints: the solution must be free and self-hostable (thesis project, no cloud budget), Docker-friendly, and academically defensible in the oral defence.

The expected scale is modest: roughly 500 wiki pages producing a few thousand nodes and tens of thousands of edges.

### Options evaluated

| Option | Graph | Vector | Python integration | Health (Feb 2026) | Notes |
|--------|-------|--------|--------------------|-------------------|-------|
| **Neo4j Community Edition** | ✅ Native Cypher | ✅ Native HNSW (v5.11+) | ✅ `neo4j-graphrag` official package | ✅ Active | JVM, ~512 MB baseline |
| KuzuDB | ✅ Cypher | ✅ HNSW extension | ⚠️ Community adapters | ❌ Archived early 2026 | Embedded, no Docker needed, but project stalled |
| FalkorDB | ✅ Cypher-compatible | ✅ Built-in | ⚠️ GraphRAG-SDK (early) | ✅ Active | Requires Redis as dependency; in-memory primary storage |
| ArangoDB Community | ✅ AQL | ⚠️ Partial integration | ⚠️ Community adapters | ✅ Active | Multi-model flexibility unused; AQL less known than Cypher |
| NetworkX + ChromaDB | ❌ In-memory only | ✅ (separate store) | ✅ | ✅ | Two systems to synchronise; no single graph+vector query |

---

## Decision

**Neo4j Community Edition** is the selected graph database.

The core reason is that the official [`neo4j-graphrag`](https://github.com/neo4j/neo4j-graphrag-python) Python package provides a `VectorCypherRetriever` class that implements exactly the required retrieval pattern:

```
embed(query) → vector ANN over node.embedding → Cypher traversal of connected subgraph → context for LLM
```

This is the GraphRAG pattern the system is built on, provided out of the box, with no custom orchestration code.

Deployment uses the official Docker image:

```yaml
# docker-compose.yml (minimal)
services:
  neo4j:
    image: neo4j:5.x-community
    ports:
      - "7474:7474"   # Browser UI
      - "7687:7687"   # Bolt protocol
    environment:
      NEO4J_AUTH: neo4j/changeme
      NEO4J_PLUGINS: '["apoc"]'
    volumes:
      - neo4j_data:/data
```

### What Neo4j is NOT used for

Embedding generation is **not** delegated to Neo4j's `genai.vector.encode()` built-ins. Those call external APIs at ingestion time and add an unnecessary dependency on OpenAI or Bedrock credentials. Instead:

- **Ingestion pipeline**: `sentence-transformers` generates embeddings in Python; the resulting vectors are written to node properties and indexed.
- **Query time**: the same `sentence-transformers` model embeds the user query in Python; Neo4j receives the vector and performs ANN + traversal.

This keeps the embedding model under local control and avoids external API calls during scraping and graph construction.

---

## Consequences

### Positive
- Single system for graph storage, graph traversal, vector search, and full-text search — no synchronisation between two stores.
- Cypher is expressive enough to encode complex multi-hop reasoning queries that form the basis of the GraphRAG vs. standard RAG comparison in the thesis evaluation.
- First-class LangChain and LangGraph integrations require zero custom adapter code.
- Neo4j is the standard academic and industry reference for knowledge graphs; citing it is clean and defensible.

### Negative / accepted trade-offs
- JVM runtime adds ~512 MB memory overhead — irrelevant at thesis scale but noted.
- Community Edition is single-instance only — no clustering. Completely irrelevant for a local, single-user system.
- Adds Docker as a hard dependency for local development.

### Constraints imposed on other decisions
- The ingestion pipeline must produce `node.embedding` properties (float arrays) before calling `CREATE VECTOR INDEX`.
- The `sentence-transformers` model used at ingestion time must be the same model used at query time; this must be pinned in configuration.
- All Cypher queries that implement multi-hop traversal must be documented in the thesis as evidence of graph-enhanced retrieval.

---

## References

- Neo4j GraphRAG Python package: <https://github.com/neo4j/neo4j-graphrag-python>
- Neo4j vector index documentation: <https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/>
- Edge, L., et al. (2024). *From Local to Global: A Graph RAG Approach to Query-Focused Summarization*. arXiv:2404.16130.
