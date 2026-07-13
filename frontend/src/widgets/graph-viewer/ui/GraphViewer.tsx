import type { Edge, Node, NodeMouseHandler, NodeTypes } from "@xyflow/react";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useQuery } from "@tanstack/react-query";
import { useTheme } from "next-themes";
import { useEffect, useMemo, useState } from "react";
import { m } from "#/paraglide/messages";
import { fetchSubgraph } from "#/shared/api/graph";
import { computeRadialLayout } from "#/widgets/graph-viewer/model/layout";
import { GraphNodeCard } from "./GraphNodeCard";
import { GraphSearch } from "./GraphSearch";

// @xyflow/react was chosen over a force-directed library (e.g.
// react-force-graph-2d) specifically for its deterministic, controlled
// layout — see model/layout.ts::computeRadialLayout. That keeps the viewer
// stable under the React Compiler and gives Playwright a fixed DOM to assert
// against, at the cost of computing node positions ourselves instead of
// getting a free force simulation.
//
// IMPORTANT: <ReactFlow> must be given an explicit `colorMode` matching the
// app's actual theme. Left unset, it defaults to "light" and stamps a literal
// class="light" on its root element — which collides with this app's own
// global `.light { --foreground: ...; }` theme selector (see styles.css) and
// re-shadows every design token back to the light palette for the whole
// graph subtree, even on an otherwise dark page. Confirmed via a full
// ancestor-chain CSS variable dump: --foreground resolved correctly down to
// `.react-flow.light`, then flipped back to the light-mode value from there
// down through every node.

const DEPTH = 2;

// Defined at module scope: a nodeTypes object that changes identity on every
// render forces React Flow to re-mount every custom node internally.
const nodeTypes: NodeTypes = { graphNode: GraphNodeCard };

interface GraphViewerProps {
  /** Optional starting node id, e.g. from a `?node=` deep link. */
  initialNodeId?: string;
}

export function GraphViewer({ initialNodeId }: GraphViewerProps) {
  const [centerId, setCenterId] = useState<string | undefined>(initialNodeId);

  // Mirror ThemeToggle.tsx's mounted-guard: next-themes only knows the real
  // resolved theme after the client mounts (defaultTheme is "system"), so
  // default to "light" pre-mount to match ReactFlow's own default and avoid a
  // hydration mismatch.
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const colorMode = mounted && resolvedTheme === "dark" ? "dark" : "light";

  const { data, isLoading, isError } = useQuery({
    queryKey: ["graph", "subgraph", centerId, DEPTH],
    queryFn: () => fetchSubgraph(centerId as string, DEPTH),
    enabled: Boolean(centerId),
  });

  const { flowNodes, flowEdges } = useMemo(() => {
    if (!data || !centerId) {
      return { flowNodes: [] as Node[], flowEdges: [] as Edge[] };
    }
    const layout = computeRadialLayout(data.nodes, data.edges, centerId);
    const positionById = new Map(
      layout.map((entry) => [entry.id, entry.position]),
    );

    const nodes: Node[] = data.nodes.map((node) => ({
      id: node.id,
      type: "graphNode",
      position: positionById.get(node.id) ?? { x: 0, y: 0 },
      data: {
        title: node.name ?? node.id,
        category: node.label,
        isCenter: node.id === centerId,
      },
    }));

    // Defensive de-dup on top of the backend's own de-dup: a duplicate
    // (source, target, rel_type) tuple would otherwise produce two React
    // elements with the same key.
    const seen = new Set<string>();
    const edges: Edge[] = [];
    for (const edge of data.edges) {
      const id = `${edge.source}--${edge.rel_type}-->${edge.target}`;
      if (seen.has(id)) continue;
      seen.add(id);
      edges.push({
        id,
        source: edge.source,
        target: edge.target,
        label: edge.rel_type,
        style: { stroke: "var(--metal)", strokeWidth: 1.25, opacity: 0.6 },
        labelStyle: { fill: "var(--muted)", fontSize: 9, fontWeight: 500 },
        labelBgStyle: { fill: "var(--surface-secondary)", fillOpacity: 0.92 },
        labelBgPadding: [4, 2],
        labelBgBorderRadius: 4,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: "var(--metal)",
        },
      });
    }

    return { flowNodes: nodes, flowEdges: edges };
  }, [data, centerId]);

  const handleNodeClick: NodeMouseHandler = (_event, node) => {
    setCenterId(node.id);
  };

  return (
    <div className="flex h-full w-full flex-col gap-3">
      <GraphSearch onSelect={setCenterId} />

      <div className="graph-flow relative flex-1 min-h-0 rounded-xl border border-border/50 bg-background overflow-hidden">
        {!centerId && (
          <div className="absolute inset-0 flex items-center justify-center p-8 text-center text-muted">
            {m.graph_empty_state()}
          </div>
        )}
        {centerId && isLoading && (
          <div className="absolute inset-0 flex items-center justify-center text-muted">
            {m.graph_loading_label()}
          </div>
        )}
        {centerId && isError && (
          <div className="absolute inset-0 flex items-center justify-center text-danger">
            {m.graph_error_label()}
          </div>
        )}
        {centerId && data && (
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            nodeTypes={nodeTypes}
            colorMode={colorMode}
            onNodeClick={handleNodeClick}
            fitView
            fitViewOptions={{ padding: 0.2, maxZoom: 1.25 }}
            minZoom={0.15}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={20} size={1} />
            <Controls showInteractive={false} />
            <MiniMap
              pannable
              zoomable
              nodeColor={(node) =>
                node.id === centerId ? "var(--accent)" : "var(--heraldic)"
              }
              className="!border !border-border/60 !rounded-lg"
            />
          </ReactFlow>
        )}
      </div>
    </div>
  );
}
