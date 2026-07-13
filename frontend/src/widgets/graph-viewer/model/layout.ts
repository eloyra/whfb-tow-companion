import type { GraphEdge, GraphNode } from "#/shared/api/graph";

export interface LayoutNode {
  id: string;
  position: { x: number; y: number };
}

const RING_SPACING = 220;

/**
 * Deterministic radial layout for the graph viewer.
 *
 * Nodes are grouped into concentric rings by BFS hop distance from
 * `centerId` (ring 0 = center, ring 1 = direct neighbors, ...), then spread
 * evenly by angle within each ring, sorted by id for a stable ordering.
 *
 * Deliberately not a force-directed simulation: the layout must be a pure
 * function of the input (same subgraph -> same positions every render), both
 * so the viewer doesn't jitter on refetch and so Playwright can assert on
 * "a node rendered" without fighting non-deterministic physics.
 */
export function computeRadialLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  centerId: string,
): LayoutNode[] {
  const adjacency = new Map<string, Set<string>>();
  for (const node of nodes) adjacency.set(node.id, new Set());
  for (const edge of edges) {
    adjacency.get(edge.source)?.add(edge.target);
    adjacency.get(edge.target)?.add(edge.source);
  }

  const distances = new Map<string, number>();
  if (adjacency.has(centerId)) {
    distances.set(centerId, 0);
    const queue: string[] = [centerId];
    while (queue.length > 0) {
      const current = queue.shift();
      if (current === undefined) break;
      const currentDistance = distances.get(current) ?? 0;
      for (const neighbor of adjacency.get(current) ?? []) {
        if (distances.has(neighbor)) continue;
        distances.set(neighbor, currentDistance + 1);
        queue.push(neighbor);
      }
    }
  }

  const rings = new Map<number, string[]>();
  for (const node of nodes) {
    // Nodes unreachable from the center (shouldn't happen — the backend only
    // returns nodes reachable via a kept edge — but fall back to an outer
    // ring rather than dropping them if it ever does).
    const distance = distances.get(node.id) ?? distances.size + 1;
    const ring = rings.get(distance) ?? [];
    ring.push(node.id);
    rings.set(distance, ring);
  }

  const positions: LayoutNode[] = [];
  for (const [ring, ids] of rings) {
    if (ring === 0) {
      for (const id of ids) positions.push({ id, position: { x: 0, y: 0 } });
      continue;
    }
    const sorted = [...ids].sort();
    const radius = ring * RING_SPACING;
    sorted.forEach((id, index) => {
      const angle = (2 * Math.PI * index) / sorted.length;
      positions.push({
        id,
        position: { x: radius * Math.cos(angle), y: radius * Math.sin(angle) },
      });
    });
  }
  return positions;
}
