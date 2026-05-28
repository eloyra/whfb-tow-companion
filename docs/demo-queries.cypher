// =============================================================================
// Warhammer: The Old World — GraphRAG Demo Queries
// For use in Neo4j Browser (graph / bubble view).
// Before running: set node caption to "name" in the Browser style panel.
// =============================================================================


// -----------------------------------------------------------------------------
// SANITY CHECK — run first to confirm full graph is loaded
// Expect: ~19 Army, hundreds of Unit, thousands of REFERENCES / HAS_RULE edges.
// If counts are tiny (1 army, 1 unit) re-run: make build-graph
// -----------------------------------------------------------------------------

MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC;

MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS n ORDER BY n DESC;


// =============================================================================
// THEME A — Faction structure
// =============================================================================

// A1. Whole Vampire Counts faction — hub-and-spoke with 33 units.
//     Demonstrates graph breadth at faction level (objective 2: army building).
MATCH p = (a:Army {id: "vampire-counts"})<-[:BELONGS_TO]-(u:Unit)
RETURN p
LIMIT 60;

// A2. One character fully expanded — troop type, rules, weapons, upgrade unlock chain.
//     Shows the structured data behind a single entry in an army list (objective 2).
MATCH (u:Unit {id: "vampire-count"})
OPTIONAL MATCH (u)-[r1:HAS_TYPE|HAS_RULE|HAS_WEAPON]->(x)
OPTIONAL MATCH (u)-[:HAS_UPGRADE]->(up:Upgrade)-[r2:UNLOCKS_WEAPON|UNLOCKS_RULE|UNLOCKS_MOUNT|UNLOCKS_ITEM]->(y)
RETURN u, r1, x, up, r2, y
LIMIT 120;


// =============================================================================
// THEME B — Rules multi-hop web  (objective 1: multi-hop rules reasoning)
// =============================================================================

// B1. Neighbourhood of Regeneration — 1-2 hop REFERENCES web.
//     "flammable" (= Flaming Attacks) and "unquiet-spirits" appear in the first
//     hop; this is the exact interaction the thesis uses as its flagship example.
//     ORDER BY length(p) guarantees all 130 direct interactors surface before the
//     2-hop tail; LIMIT 200 keeps the bubble view readable.
MATCH p = (n {id: "regeneration"})-[:REFERENCES*1..2]-(m)
RETURN p
ORDER BY length(p)
LIMIT 200;

// B2. Shortest path: flammable → unstable (routes through regeneration).
//     Demonstrates the graph traversal pattern used by the RAG layer to
//     bridge two concepts a player might ask about in a single question.
MATCH p = shortestPath(
  (a {id: "flammable"})-[:REFERENCES*..4]-(b {id: "unstable"})
)
RETURN p;


// =============================================================================
// THEME C — Magic + FAQ / Errata layer
// =============================================================================

// C1. Battle Magic lore: its 7 spells and every army that accesses it.
//     Shows graph breadth across magic system (lore → spells, army → lore).
MATCH (l:Lore {id: "battle-magic"})
OPTIONAL MATCH (s:Spell)-[:BELONGS_TO_LORE]->(l)
OPTIONAL MATCH (a:Army)-[:USES_LORE]->(l)
RETURN l, s, a;

// C2. Official ruling overlay — all FAQ and Errata nodes hanging off the
//     rules they clarify or amend.  Shows the graph encodes authoritative
//     corrections on top of the base rules (474 CLARIFIES + 385 AMENDS edges).
MATCH p = (d)-[:CLARIFIES|AMENDS]->(t)
WHERE d:FAQ OR d:Errata
RETURN p
LIMIT 40;

// C3. Finale — Unit → SpecialRule ← FAQ in one path.
//     The system's whole value proposition: a player's unit has a rule, and
//     there is an official FAQ ruling on it.  1561 such unit→rule links exist.
MATCH p = (u:Unit)-[:HAS_RULE]->(r)<-[:CLARIFIES]-(f:FAQ)
RETURN p
LIMIT 30;
