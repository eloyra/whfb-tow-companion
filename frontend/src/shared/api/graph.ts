import { z } from "zod";
import { env } from "#/shared/config/env";

/**
 * Typed REST client for the backend's `/graph` endpoints (see
 * `backend/api/routes/graph.py`), used by the `graph-viewer` widget.
 *
 * Mirrors `features/chat/model/graph-source.ts`'s lenient-parsing style:
 * `safeParse` against the wire shape, `null` on failure (network error or a
 * malformed payload) rather than throwing — a broken graph fetch should
 * degrade the viewer to an empty state, not crash the page.
 */

const lenientString = () =>
  z
    .string()
    .nullish()
    .transform((value) => value ?? undefined)
    .optional();

export const graphNodeSchema = z.object({
  id: z.string(),
  label: lenientString(),
  name: lenientString(),
  source_url: lenientString(),
});
export type GraphNode = z.infer<typeof graphNodeSchema>;

export const graphEdgeSchema = z.object({
  source: z.string(),
  target: z.string(),
  rel_type: z.string(),
});
export type GraphEdge = z.infer<typeof graphEdgeSchema>;

const nodeListResponseSchema = z.object({
  nodes: z.array(graphNodeSchema),
});

const subgraphResponseSchema = z.object({
  nodes: z.array(graphNodeSchema),
  edges: z.array(graphEdgeSchema),
});
export type SubgraphResponse = z.infer<typeof subgraphResponseSchema>;

export interface FetchNodesParams {
  nodeType?: string;
  q?: string;
  limit?: number;
}

/**
 * Fetch nodes for the graph viewer's search/browse entry point.
 *
 * `nodeType`/`q`/`limit` map to the backend's `node_type`/`q`/`limit` query
 * params on `GET /graph/nodes`.
 */
export async function fetchNodes(
  params: FetchNodesParams = {},
): Promise<GraphNode[] | null> {
  const search = new URLSearchParams();
  if (params.nodeType) search.set("node_type", params.nodeType);
  if (params.q) search.set("q", params.q);
  if (params.limit) search.set("limit", String(params.limit));

  try {
    const response = await fetch(
      `${env.apiUrl}/graph/nodes?${search.toString()}`,
    );
    if (!response.ok) {
      console.warn("[Graph] /graph/nodes request failed", response.status);
      return null;
    }
    const result = nodeListResponseSchema.safeParse(await response.json());
    if (!result.success) {
      console.warn("[Graph] Failed to parse node list", result.error.format());
      return null;
    }
    return result.data.nodes;
  } catch (error) {
    console.warn("[Graph] /graph/nodes request threw", error);
    return null;
  }
}

/**
 * Fetch a bounded multi-hop neighborhood around `nodeId` for the graph
 * viewer's re-center-on-click interaction.
 */
export async function fetchSubgraph(
  nodeId: string,
  depth = 2,
): Promise<SubgraphResponse | null> {
  try {
    const response = await fetch(
      `${env.apiUrl}/graph/subgraph/${encodeURIComponent(nodeId)}?depth=${depth}`,
    );
    if (!response.ok) {
      console.warn("[Graph] /graph/subgraph request failed", response.status);
      return null;
    }
    const result = subgraphResponseSchema.safeParse(await response.json());
    if (!result.success) {
      console.warn(
        "[Graph] Failed to parse subgraph response",
        result.error.format(),
      );
      return null;
    }
    return result.data;
  } catch (error) {
    console.warn("[Graph] /graph/subgraph request threw", error);
    return null;
  }
}
