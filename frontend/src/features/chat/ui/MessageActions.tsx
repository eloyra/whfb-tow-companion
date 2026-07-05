import { Button } from "@heroui/react";
import type { UIMessage } from "ai";
import { Copy, RotateCcw } from "lucide-react";
import { useState } from "react";
import { m } from "#/paraglide/messages";
import { cn } from "#/shared/lib/utils";

interface MessageActionsProps {
  message: UIMessage;
  canRegenerate: boolean;
  onRegenerate?: () => void;
  className?: string;
}

function extractCopyText(message: UIMessage): string {
  return message.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("\n\n");
}

/**
 * Hover-overlay actions for a chat message: copy text and regenerate.
 * Visible on hover and keyboard focus for accessibility.
 */
export function MessageActions({
  message,
  canRegenerate,
  onRegenerate,
  className,
}: MessageActionsProps) {
  const [copied, setCopied] = useState(false);
  const text = extractCopyText(message);

  async function handleCopy() {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fail silently — the action is a convenience, not critical.
    }
  }

  return (
    <div
      className={cn(
        "flex items-center gap-1 opacity-0 transition-opacity duration-200",
        "group-hover:opacity-100 focus-within:opacity-100",
        className,
      )}
    >
      {text && (
        <Button
          isIconOnly
          size="sm"
          variant="ghost"
          onPress={handleCopy}
          aria-label={m.chat_copy_button()}
          className={cn("h-7 w-7 min-w-0", copied && "text-success")}
        >
          <Copy size={14} aria-hidden="true" />
        </Button>
      )}

      {canRegenerate && onRegenerate && (
        <Button
          isIconOnly
          size="sm"
          variant="ghost"
          onPress={() => void onRegenerate()}
          aria-label={m.chat_regenerate_button()}
          className="h-7 w-7 min-w-0"
        >
          <RotateCcw size={14} aria-hidden="true" />
        </Button>
      )}
    </div>
  );
}
