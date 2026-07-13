import type { Edge, Node, NodeMouseHandler } from "@xyflow/react";
import { Background, Controls, MiniMap, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { m } from "#/paraglide/messages";
import { fetchSubgraph } from "#/shared/api/graph";
import { computeRadialLayout } from "#/widgets/graph-viewer/model/layout";
import { GraphSearch } from "./GraphSearch";

// @xyflow/react was chosen over a force-directed library (e.g.
// react-force-graph-2d) specifically for its deterministic, controlled
// layout — see model/layout.ts::computeRadialLayout. That keeps the viewer
// stable under the React Compiler and gives Playwright a fixed DOM to assert
// against, at the cost of computing node positions ourselves instead of
// getting a free force simulation.

const DEPTH = 2;

interface GraphViewerProps {
  /** Optional starting node id, e.g. from a `?node=` deep link. */
  initialNodeId?: string;
}

export function GraphViewer({ initialNodeId }: GraphViewerProps) {
  const [centerId, setCenterId] = useState<string | undefined>(initialNodeId);

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
      position: positionById.get(node.id) ?? { x: 0, y: 0 },
      data: {
        label: node.label
          ? `${node.name ?? node.id} (${node.label})`
          : (node.name ?? node.id),
      },
      className:
        node.id === centerId
          ? "border-2 border-accent bg-accent/10 text-foreground rounded-lg px-2 py-1 text-xs"
          : "border border-metal/40 bg-surface text-foreground rounded-lg px-2 py-1 text-xs",
    }));

    const edges: Edge[] = data.edges.map((edge) => ({
      id: `${edge.source}--${edge.rel_type}-->${edge.target}`,
      source: edge.source,
      target: edge.target,
      label: edge.rel_type,
      className: "text-[10px] text-muted",
    }));

    return { flowNodes: nodes, flowEdges: edges };
  }, [data, centerId]);

  const handleNodeClick: NodeMouseHandler = (_event, node) => {
    setCenterId(node.id);
  };

  return (
    <div className="flex h-full w-full flex-col gap-3">
      <GraphSearch onSelect={setCenterId} />

      <div className="relative flex-1 min-h-0 rounded-xl border border-border/50 bg-background/60 overflow-hidden">
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
            onNodeClick={handleNodeClick}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>
        )}
      </div>
    </div>
  );
}
