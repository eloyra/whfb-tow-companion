import { useChat } from "@ai-sdk/react";
import { Alert, Button, Card, TextArea } from "@heroui/react";
import { DefaultChatTransport } from "ai";
import { Scroll } from "lucide-react";
import type { KeyboardEvent } from "react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { parseGraphSources } from "#/features/chat/model/graph-source";
import { SourcesList } from "#/features/chat/ui/SourcesList";
import { m } from "#/paraglide/messages";
import { env } from "#/shared/config/env";
import { cn } from "#/shared/lib/utils";

export function ChatInterface() {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const { messages, sendMessage, status, error, stop, regenerate, clearError } =
    useChat({
      transport: new DefaultChatTransport({
        api: `${env.apiUrl}/chat/`,
      }),
      onError: (err) => console.error("Chat API Error:", err),
    });

  // biome-ignore lint/correctness/useExhaustiveDependencies: messages triggers scroll; body uses stable ref
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distanceFromBottom < 100) {
      scrollRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  useEffect(
    () => () => {
      stop();
    },
    [stop],
  );

  const isStreaming = status === "submitted" || status === "streaming";

  function doSend(textToSend?: string) {
    const text = textToSend ?? input;
    if (!text.trim() || isStreaming) return;
    sendMessage({ text }).catch((err) =>
      console.error("Error sending message:", err),
    );
    setInput("");
    inputRef.current?.focus();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      doSend();
    }
  }

  const lastMsg = messages[messages.length - 1];

  return (
    <div className="flex flex-col h-full w-full max-w-4xl mx-auto border border-border/50 rounded-xl bg-background/50 backdrop-blur-sm overflow-hidden shadow-lg">
      {error && (
        <Alert status="danger" className="m-2 rounded-lg shrink-0">
          <Alert.Content>
            <Alert.Title>{m.chat_error_title()}</Alert.Title>
            <Alert.Description>{error.message}</Alert.Description>
          </Alert.Content>
          <Button
            size="sm"
            variant="ghost"
            onPress={() => {
              clearError();
              void regenerate();
            }}
          >
            {m.chat_error_retry()}
          </Button>
        </Alert>
      )}

      {/* MESSAGE HISTORY */}
      <div
        ref={scrollContainerRef}
        role="log"
        aria-live="polite"
        aria-label={m.chat_history_label()}
        className="flex-1 overflow-y-auto p-4 space-y-6"
      >
        {messages.length === 0 ? (
          <EmptyState onSelect={doSend} />
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={cn(
                "flex w-full",
                msg.role === "user" ? "justify-end" : "justify-start",
              )}
            >
              <Card
                className={cn(
                  "max-w-[80%]",
                  msg.role === "user" ? "bg-accent" : "bg-surface",
                )}
              >
                <Card.Content className="py-3 px-4 space-y-2">
                  {msg.parts.map((part, index) => {
                    if (part.type === "text") {
                      const isUser = msg.role === "user";
                      return (
                        <div
                          // biome-ignore lint/suspicious/noArrayIndexKey: text parts have no stable id
                          key={index}
                          className={cn(
                            "max-w-none",
                            isUser
                              ? "text-accent-foreground whitespace-pre-wrap"
                              : "prose prose-sm dark:prose-invert",
                          )}
                        >
                          {isUser ? (
                            part.text
                          ) : (
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              rehypePlugins={[rehypeSanitize]}
                            >
                              {part.text}
                            </ReactMarkdown>
                          )}
                        </div>
                      );
                    }

                    if (part.type === "reasoning") {
                      return (
                        <details
                          // biome-ignore lint/suspicious/noArrayIndexKey: parts have no stable id
                          key={index}
                          className="text-xs opacity-60"
                        >
                          <summary className="cursor-pointer select-none">
                            Reasoning
                          </summary>
                          <pre className="whitespace-pre-wrap mt-1 font-mono">
                            {part.text}
                          </pre>
                        </details>
                      );
                    }

                    if (part.type === "source-url") {
                      return (
                        <a
                          // biome-ignore lint/suspicious/noArrayIndexKey: parts have no stable id
                          key={index}
                          href={part.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs underline opacity-70 block"
                        >
                          {part.title ?? part.url}
                        </a>
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

                  {msg.role === "assistant" &&
                    lastMsg?.id === msg.id &&
                    !isStreaming && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onPress={() => void regenerate()}
                        aria-label={m.chat_regenerate_button()}
                        className="mt-1 -ml-1"
                      >
                        {m.chat_regenerate_button()}
                      </Button>
                    )}
                </Card.Content>
              </Card>
            </div>
          ))
        )}

        {isStreaming && lastMsg?.role === "user" && (
          <div className="flex justify-start">
            <Card className="opacity-70">
              <Card.Content className="py-3 px-4 flex flex-row gap-1 items-center">
                <div className="w-2 h-2 rounded-full bg-current animate-bounce" />
                <div className="w-2 h-2 rounded-full bg-current animate-bounce [animation-delay:0.2s]" />
                <div className="w-2 h-2 rounded-full bg-current animate-bounce [animation-delay:0.4s]" />
              </Card.Content>
            </Card>
          </div>
        )}

        <div ref={scrollRef} aria-hidden="true" />
      </div>

      {/* INPUT AREA */}
      <div className="p-4 bg-content1 border-t border-border/50 shrink-0">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            doSend();
          }}
          className="flex gap-2 items-end"
        >
          <TextArea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={m.chat_input_placeholder()}
            aria-label={m.chat_input_placeholder()}
            fullWidth
            variant="primary"
            disabled={isStreaming}
            className="text-base resize-none"
            rows={2}
          />

          {isStreaming ? (
            <Button
              type="button"
              variant="secondary"
              onPress={() => stop()}
              aria-label={m.chat_stop_button()}
            >
              {m.chat_stop_button()}
            </Button>
          ) : (
            <Button
              type="submit"
              variant="primary"
              isDisabled={!input.trim()}
              aria-label={m.chat_send_button()}
            >
              {m.chat_send_button()}
            </Button>
          )}
        </form>
      </div>
    </div>
  );
}

interface EmptyStateProps {
  onSelect: (text: string) => void;
}

function EmptyState({ onSelect }: EmptyStateProps) {
  const examples = [m.chat_example_1(), m.chat_example_2(), m.chat_example_3()];

  return (
    <div className="h-full flex flex-col items-center justify-center text-center px-2">
      <div className="mb-6 rounded-full border border-border/50 bg-surface p-4">
        <Scroll className="h-8 w-8 text-accent" aria-hidden="true" />
      </div>

      <h2 className="text-xl font-display font-bold text-foreground mb-2">
        {m.chat_empty_title()}
      </h2>
      <p className="max-w-md text-muted mb-6">{m.chat_empty_description()}</p>

      <div className="w-full max-w-lg">
        <p className="text-xs font-medium text-muted mb-3">
          {m.chat_example_prompt()}
        </p>
        <div className="flex flex-col gap-3">
          {examples.map((query) => (
            <button
              key={query}
              type="button"
              onClick={() => onSelect(query)}
              className="text-left rounded-xl border border-border/50 bg-surface p-3 transition-colors hover:bg-surface-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <p className="text-sm text-foreground">{query}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
