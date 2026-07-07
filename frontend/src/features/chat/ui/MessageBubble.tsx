import { Card } from "@heroui/react";
import type { UIMessage } from "ai";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { parseGraphSources } from "#/features/chat/model/graph-source";
import { SourcesList } from "#/features/chat/ui/SourcesList";
import { m } from "#/paraglide/messages";
import { cn } from "#/shared/lib/utils";
import { MessageActions } from "./MessageActions";
import { RoleAvatar } from "./RoleAvatar";

interface MessageBubbleProps {
  message: UIMessage;
  isLast: boolean;
  isStreaming: boolean;
  onRegenerate?: () => void;
}

const ROLE_LABELS: Record<string, string> = {
  assistant: m.chat_role_assistant(),
  system: m.chat_role_assistant(),
  user: m.chat_role_user(),
};

function ReasoningBlock({ text }: { text: string }) {
  return (
    <details className="group/reasoning text-xs">
      <summary className="cursor-pointer select-none inline-flex items-center gap-1.5 text-metal-foreground font-display uppercase tracking-wider">
        <span className="w-4 h-px bg-metal/60" aria-hidden="true" />
        Reasoning
      </summary>
      <pre className="mt-2 p-3 rounded-md bg-surface-secondary text-foreground/80 whitespace-pre-wrap font-mono text-[11px] leading-relaxed border border-border/50">
        {text}
      </pre>
    </details>
  );
}

function SourceUrl({ url, title }: { url: string; title?: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-xs text-heraldic underline underline-offset-2 hover:text-heraldic/80"
    >
      {title ?? url}
    </a>
  );
}

/**
 * A single chat message with role avatar, eyebrow label, content parts,
 * and hover actions.
 */
export function MessageBubble({
  message,
  isLast,
  isStreaming,
  onRegenerate,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const displayRole: "user" | "assistant" = isUser ? "user" : "assistant";
  const canRegenerate =
    displayRole === "assistant" && isLast && !isStreaming && onRegenerate;

  return (
    <div
      className={cn(
        "group flex w-full gap-3",
        isUser ? "flex-row-reverse" : "flex-row",
      )}
    >
      <RoleAvatar role={displayRole} size={28} />

      <div
        className={cn(
          "flex min-w-0 flex-col",
          isUser ? "items-end" : "items-start",
        )}
      >
        {/* Eyebrow + actions */}
        <div
          className={cn(
            "mb-1 flex w-full items-center gap-2",
            isUser ? "flex-row-reverse" : "flex-row",
          )}
        >
          <span className="font-display text-[10px] uppercase tracking-[0.12em] text-metal-foreground">
            {ROLE_LABELS[displayRole]}
          </span>
          {!isUser && (
            <MessageActions
              message={message}
              canRegenerate={!!canRegenerate}
              onRegenerate={onRegenerate}
            />
          )}
        </div>

        {/* Bubble */}
        <Card
          className={cn(
            "message-enter w-fit",
            isUser
              ? "max-w-[85%] md:max-w-2xl bg-slate text-slate-foreground rounded-2xl rounded-tr-sm border-0"
              : "max-w-[90%] md:max-w-3xl bg-surface text-surface-foreground rounded-2xl rounded-tl-sm border border-border/50 shadow-sm",
          )}
        >
          <Card.Content className="px-4 py-3 space-y-3">
            {message.parts.map((part, index) => {
              if (part.type === "text") {
                return isUser ? (
                  <div
                    // biome-ignore lint/suspicious/noArrayIndexKey: text parts have no stable id
                    key={index}
                    className="whitespace-pre-wrap text-[15px] leading-relaxed"
                  >
                    {part.text}
                  </div>
                ) : (
                  <div
                    // biome-ignore lint/suspicious/noArrayIndexKey: text parts have no stable id
                    key={index}
                    className="prose prose-sm max-w-none dark:prose-invert prose-a:text-accent prose-a:no-underline hover:prose-a:underline prose-headings:font-display prose-headings:tracking-wide prose-code:text-foreground prose-pre:bg-surface-secondary prose-pre:border prose-pre:border-border/50"
                  >
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      rehypePlugins={[rehypeSanitize]}
                    >
                      {part.text}
                    </ReactMarkdown>
                  </div>
                );
              }

              if (part.type === "reasoning") {
                return (
                  // biome-ignore lint/suspicious/noArrayIndexKey: reasoning parts have no stable id
                  <ReasoningBlock key={index} text={part.text} />
                );
              }

              if (part.type === "source-url") {
                return (
                  // biome-ignore lint/suspicious/noArrayIndexKey: source-url parts have no stable id
                  <SourceUrl key={index} url={part.url} title={part.title} />
                );
              }

              if (part.type === "data-sources") {
                const sources = parseGraphSources(part.data);
                if (sources === null) {
                  // Lenient reader: malformed source payload is dropped
                  // without crashing the stream.
                  return null;
                }
                return (
                  <SourcesList
                    key={part.id ?? `sources-${index}`}
                    sources={sources}
                  />
                );
              }

              // step-start and unrecognised parts: skip silently
              return null;
            })}
          </Card.Content>
        </Card>
      </div>
    </div>
  );
}
