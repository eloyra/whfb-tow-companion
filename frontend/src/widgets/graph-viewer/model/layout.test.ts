import { describe, expect, it } from "vitest";

import type { GraphEdge, GraphNode } from "#/shared/api/graph";
import { computeRadialLayout } from "./layout";

function node(id: string): GraphNode {
  return { id };
}

function edge(
  source: string,
  target: string,
  relType = "REFERENCES",
): GraphEdge {
  return { source, target, rel_type: relType };
}

describe("computeRadialLayout", () => {
  it("places the center node at the origin", () => {
    const nodes = [node("fear"), node("terror")];
    const edges = [edge("fear", "terror")];

    const layout = computeRadialLayout(nodes, edges, "fear");

    expect(layout.find((entry) => entry.id === "fear")?.position).toEqual({
      x: 0,
      y: 0,
    });
  });

  it("places 1-hop neighbors on a ring closer than 2-hop neighbors", () => {
    // fear -> terror -> stubborn (2 hops from fear)
    const nodes = [node("fear"), node("terror"), node("stubborn")];
    const edges = [edge("fear", "terror"), edge("terror", "stubborn")];

    const layout = computeRadialLayout(nodes, edges, "fear");
    const distanceFromOrigin = (id: string) => {
      const position = layout.find((entry) => entry.id === id)?.position;
      if (!position) throw new Error(`missing layout for ${id}`);
      return Math.hypot(position.x, position.y);
    };

    expect(distanceFromOrigin("terror")).toBeGreaterThan(0);
    expect(distanceFromOrigin("stubborn")).toBeGreaterThan(
      distanceFromOrigin("terror"),
    );
  });

  it("treats edges as undirected when computing hop distance", () => {
    // Edge direction is target -> center; center should still be ring 0 and
    // the other endpoint ring 1 (subgraphAll edges carry real direction, but
    // fan-out/hop-distance is symmetric).
    const nodes = [node("ghoul-king"), node("fear")];
    const edges = [edge("ghoul-king", "fear", "HAS_RULE")];

    const layout = computeRadialLayout(nodes, edges, "fear");

    expect(layout.find((entry) => entry.id === "fear")?.position).toEqual({
      x: 0,
      y: 0,
    });
    expect(
      layout.find((entry) => entry.id === "ghoul-king")?.position,
    ).not.toEqual({
      x: 0,
      y: 0,
    });
  });

  it("is a pure function of its input — identical calls produce identical positions", () => {
    const nodes = [node("a"), node("b"), node("c"), node("d")];
    const edges = [edge("a", "b"), edge("a", "c"), edge("a", "d")];

    const first = computeRadialLayout(nodes, edges, "a");
    const second = computeRadialLayout(nodes, edges, "a");

    expect(second).toEqual(first);
  });

  it("returns a position for every input node, even with no edges", () => {
    const nodes = [node("solo")];

    const layout = computeRadialLayout(nodes, [], "solo");

    expect(layout).toEqual([{ id: "solo", position: { x: 0, y: 0 } }]);
  });
});
