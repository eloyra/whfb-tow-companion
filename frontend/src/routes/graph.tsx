import { createFileRoute } from "@tanstack/react-router";
import { AppHeader } from "#/shared/ui";
import { GraphViewer } from "#/widgets/graph-viewer";

interface GraphSearch {
  node?: string;
}

export const Route = createFileRoute("/graph")({
  component: GraphPage,
  validateSearch: (search: Record<string, unknown>): GraphSearch => ({
    node: typeof search.node === "string" ? search.node : undefined,
  }),
});

function GraphPage() {
  const { node } = Route.useSearch();

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      <AppHeader />
      <main className="flex flex-1 min-h-0 flex-col px-4 sm:px-8 py-4">
        <GraphViewer initialNodeId={node} />
      </main>
    </div>
  );
}
