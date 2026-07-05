import { Chip, Tooltip } from "@heroui/react";
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
  const tooltipContent =
    [source.label, source.text].filter(Boolean).join(" — ") || source.id;

  const chip = (
    <Tooltip>
      <Tooltip.Trigger>
        <Chip
          size="sm"
          className="cursor-default border border-heraldic/20 bg-heraldic/10 text-heraldic hover:bg-heraldic/15"
        >
          {source.id}
        </Chip>
      </Tooltip.Trigger>
      <Tooltip.Content>
        <p className="text-xs max-w-xs">{tooltipContent}</p>
      </Tooltip.Content>
    </Tooltip>
  );

  if (source.source_url && isValidUrl(source.source_url)) {
    return (
      <a
        href={source.source_url}
        target="_blank"
        rel="noreferrer"
        className="inline-block"
      >
        {chip}
      </a>
    );
  }

  return chip;
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
        <p className="font-display text-[10px] uppercase tracking-[0.12em] text-metal">
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
