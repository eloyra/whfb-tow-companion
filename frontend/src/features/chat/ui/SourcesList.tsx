import { Chip } from "@heroui/react";
import { Link } from "@tanstack/react-router";
import { Network } from "lucide-react";
import type { GraphSource } from "#/features/chat/model/graph-source";
import { m } from "#/paraglide/messages";

interface SourcesListProps {
  sources: GraphSource[];
}

function isValidUrl(value: string): boolean {
  try {
    new URL(value);
    return true;
  } catch {
    return false;
  }
}

function SourceChip({ source }: { source: GraphSource }) {
  const displayName = source.name || source.id;
  const tooltipContent =
    [source.label, source.text].filter(Boolean).join(" — ") || displayName;

  const chip = (
    <Chip
      size="sm"
      className="cursor-default border border-heraldic/20 bg-heraldic/10 text-heraldic hover:bg-heraldic/15"
    >
      {displayName}
    </Chip>
  );

  const graphLink = (
    <Link
      to="/graph"
      search={{ node: source.id }}
      aria-label={`${m.chat_view_in_graph()}: ${displayName}`}
      title={m.chat_view_in_graph()}
      className="inline-flex items-center justify-center rounded-full p-1 text-heraldic/70 hover:text-heraldic hover:bg-heraldic/10 transition-colors"
    >
      <Network size={12} aria-hidden="true" />
    </Link>
  );

  if (source.source_url && isValidUrl(source.source_url)) {
    return (
      <div className="inline-flex items-center gap-0.5">
        <div className="relative inline-block group">
          <a
            href={source.source_url}
            target="_blank"
            rel="noreferrer"
            className="inline-block"
            aria-describedby={`source-tooltip-${source.id}`}
          >
            {chip}
          </a>
          <div
            id={`source-tooltip-${source.id}`}
            role="tooltip"
            className="absolute left-0 bottom-full mb-2 z-50 hidden w-80 group-hover:block"
          >
            <div className="rounded-md border border-metal/20 bg-background shadow-lg overflow-hidden">
              <iframe
                src={source.source_url}
                title={displayName}
                loading="lazy"
                className="w-full h-48 border-0 bg-white"
              />
            </div>
            <p className="text-xs text-muted mt-1 px-1">{tooltipContent}</p>
          </div>
        </div>
        {graphLink}
      </div>
    );
  }

  return (
    <div className="inline-flex items-center gap-0.5">
      {chip}
      {graphLink}
    </div>
  );
}

/**
 * Renders the graph nodes that the backend retrieved and cited for an
 * assistant reply.
 */
export function SourcesList({ sources }: SourcesListProps) {
  return (
    <div className="pt-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="w-4 h-px bg-metal/60" aria-hidden="true" />
        <p className="font-display text-[10px] uppercase tracking-[0.12em] text-metal-foreground">
          {m.chat_sources_label()}
        </p>
      </div>

      {sources.length === 0 ? (
        <p className="text-xs text-muted italic">{m.chat_no_sources()}</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {sources.map((source) => (
            <SourceChip key={source.id} source={source} />
          ))}
        </div>
      )}
    </div>
  );
}
