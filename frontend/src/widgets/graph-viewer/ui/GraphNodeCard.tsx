import type { NodeProps } from "@xyflow/react";
import { Handle, Position } from "@xyflow/react";
import { cn } from "#/shared/lib/utils";

export interface GraphNodeData extends Record<string, unknown> {
  title: string;
  category?: string;
  isCenter: boolean;
}

const handleClassName = "!h-1.5 !w-1.5 !border-none !bg-metal/60";

/**
 * Custom node renderer for the graph viewer.
 *
 * Replaces @xyflow/react's built-in default node (which ships its own
 * light-themed background/border baked into its stylesheet, independent of
 * our design tokens) so every node reliably follows the app's light/dark
 * theme via the same CSS variables as the rest of the UI.
 */
export function GraphNodeCard(props: NodeProps) {
  const data = props.data as GraphNodeData;

  return (
    <div
      className={cn(
        "min-w-[110px] max-w-[220px] rounded-lg border px-3 py-1.5 text-xs shadow-sm transition-colors",
        data.isCenter
          ? "border-accent bg-accent/15 font-semibold text-foreground ring-2 ring-accent/30"
          : "border-heraldic/35 bg-surface text-surface-foreground hover:border-heraldic/70 hover:bg-heraldic/10",
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className={handleClassName}
      />
      <p className="truncate leading-snug" title={data.title}>
        {data.title}
      </p>
      {data.category && (
        <p className="mt-0.5 truncate text-[9px] uppercase tracking-wide text-muted">
          {data.category}
        </p>
      )}
      <Handle
        type="source"
        position={Position.Bottom}
        className={handleClassName}
      />
    </div>
  );
}
