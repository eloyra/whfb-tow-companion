import { Input } from "@heroui/react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { m } from "#/paraglide/messages";
import { fetchNodes } from "#/shared/api/graph";

interface GraphSearchProps {
  onSelect: (nodeId: string) => void;
}

const DEBOUNCE_MS = 300;
const RESULT_LIMIT = 10;

/**
 * Name-prefix search box hitting `GET /graph/nodes?q=` — the graph viewer's
 * entry point for picking a starting node.
 */
export function GraphSearch({ onSelect }: GraphSearchProps) {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  useEffect(() => {
    const timer = setTimeout(
      () => setDebouncedQuery(query.trim()),
      DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [query]);

  const { data } = useQuery({
    queryKey: ["graph", "nodes", debouncedQuery],
    queryFn: () => fetchNodes({ q: debouncedQuery, limit: RESULT_LIMIT }),
    enabled: debouncedQuery.length > 0,
  });

  const results = data ?? [];

  function selectNode(nodeId: string) {
    onSelect(nodeId);
    setQuery("");
    setDebouncedQuery("");
  }

  return (
    <div className="relative">
      <div className="relative">
        <Search
          size={16}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
          aria-hidden="true"
        />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={m.graph_search_placeholder()}
          aria-label={m.graph_search_label()}
          fullWidth
          variant="primary"
          className="pl-9"
        />
      </div>

      {debouncedQuery.length > 0 && (
        <div className="absolute z-10 mt-1 w-full rounded-lg border border-metal/30 bg-surface shadow-lg overflow-hidden">
          {results.length === 0 ? (
            <p className="px-3 py-2 text-sm text-muted italic">
              {m.graph_no_results()}
            </p>
          ) : (
            <ul className="max-h-72 overflow-y-auto">
              {results.map((node) => (
                <li key={node.id}>
                  <button
                    type="button"
                    onClick={() => selectNode(node.id)}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-surface-secondary focus-visible:outline-none focus-visible:bg-surface-secondary"
                  >
                    <span className="text-foreground">
                      {node.name ?? node.id}
                    </span>
                    {node.label && (
                      <span className="ml-2 text-xs text-muted">
                        {node.label}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
