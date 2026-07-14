import { Chip } from "@heroui/react";
import { Link } from "@tanstack/react-router";
import { Network } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { GraphSource } from "#/features/chat/model/graph-source";
import { m } from "#/paraglide/messages";

// Grace period before hiding the preview after the mouse leaves the trigger
// or the preview itself. Without it, moving the mouse from the chip up to
// the (gapped, portaled) preview card passes through dead space that belongs
// to neither element, firing mouseleave before the card's own mouseenter —
// closing the card before the pointer ever reaches it, which makes its
// scrollable text unreachable by mouse.
const HIDE_DELAY_MS = 200;

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

interface PreviewPosition {
  top: number;
  left: number;
}

function citationLine(source: GraphSource): string | null {
  if (!source.book) return null;
  return source.page != null
    ? `${source.book}, p. ${source.page}`
    : source.book;
}

/**
 * Hover preview card: the node's own name/label/text. Renders our own themed
 * content rather than embedding the external wiki in an iframe — the iframe
 * showed the target site's own header/nav (which dominates a small preview
 * and can't be cropped without cross-origin script access to scroll it), and
 * offered no benefit over text we already have.
 *
 * Rendered through a portal to `document.body`, positioned from the
 * trigger's own bounding rect. This is deliberate, not decorative: the
 * message bubble (`Card` in MessageBubble.tsx) has `overflow-hidden` for its
 * rounded corners, which clips anything absolutely positioned inside it — a
 * portal is the standard way to escape a clipped ancestor.
 */
function SourcePreview({
  source,
  position,
  tooltipId,
  onMouseEnter,
  onMouseLeave,
}: {
  source: GraphSource;
  position: PreviewPosition;
  tooltipId: string;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}) {
  const displayName = source.name || source.id;
  const citation = citationLine(source);

  return createPortal(
    <div
      id={tooltipId}
      role="tooltip"
      className="fixed z-50 w-64"
      style={{
        top: position.top,
        left: position.left,
        transform: "translateY(-100%)",
      }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="mb-2 rounded-lg border border-metal/25 bg-surface shadow-lg overflow-hidden">
        <div className="flex items-start justify-between gap-2 border-b border-metal/15 bg-surface-secondary px-3 py-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-surface-foreground">
              {displayName}
            </p>
            {citation && <p className="text-[10px] text-muted">{citation}</p>}
          </div>
          {source.label && (
            <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted">
              {source.label}
            </span>
          )}
        </div>
        {source.text && (
          <p className="max-h-40 overflow-y-auto px-3 py-2 text-xs leading-relaxed text-surface-foreground/90">
            {source.text}
          </p>
        )}
      </div>
    </div>,
    document.body,
  );
}

function SourceChip({ source }: { source: GraphSource }) {
  const [position, setPosition] = useState<PreviewPosition | null>(null);
  const triggerRef = useRef<HTMLDivElement>(null);
  const hideTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tooltipId = useId();
  const displayName = source.name || source.id;
  const hasPreview = Boolean(source.text || source.label);
  const hasValidUrl = Boolean(
    source.source_url && isValidUrl(source.source_url),
  );

  useEffect(() => {
    return () => {
      if (hideTimeoutRef.current) clearTimeout(hideTimeoutRef.current);
    };
  }, []);

  function cancelHide() {
    if (hideTimeoutRef.current) {
      clearTimeout(hideTimeoutRef.current);
      hideTimeoutRef.current = null;
    }
  }

  function showPreview() {
    cancelHide();
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPosition({ top: rect.top - 8, left: rect.left });
  }

  function scheduleHide() {
    cancelHide();
    hideTimeoutRef.current = setTimeout(() => {
      setPosition(null);
    }, HIDE_DELAY_MS);
  }

  function hidePreview() {
    cancelHide();
    setPosition(null);
  }

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

  return (
    <div className="inline-flex items-center gap-0.5">
      {/* biome-ignore lint/a11y/noStaticElementInteractions: not an independent
          control — it only relays hover/focus bubbling from the real
          interactive child (the <a>, when present) to show/hide the portaled
          preview. Giving it its own role would create a nested-interactive
          element around that <a>, the exact anti-pattern this file's git
          history already had to fix once (HeroUI's Tooltip.Trigger wrapper
          did this). */}
      <div
        ref={triggerRef}
        className="relative inline-block"
        onMouseEnter={hasPreview ? showPreview : undefined}
        onMouseLeave={hasPreview ? scheduleHide : undefined}
        onFocus={hasPreview ? showPreview : undefined}
        onBlur={hasPreview ? hidePreview : undefined}
      >
        {hasValidUrl ? (
          <a
            href={source.source_url}
            target="_blank"
            rel="noreferrer"
            className="inline-block"
            aria-describedby={hasPreview ? tooltipId : undefined}
          >
            {chip}
          </a>
        ) : (
          chip
        )}
      </div>
      {hasPreview && position && (
        <SourcePreview
          source={source}
          position={position}
          tooltipId={tooltipId}
          onMouseEnter={cancelHide}
          onMouseLeave={scheduleHide}
        />
      )}
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
