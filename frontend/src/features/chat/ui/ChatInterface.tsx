import { useChat } from "@ai-sdk/react";
import { Alert, Button, Card, TextArea } from "@heroui/react";
import { DefaultChatTransport } from "ai";
import { ChevronDown, Scroll, Send, Square } from "lucide-react";
import type { KeyboardEvent, UIEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { MessageBubble } from "#/features/chat/ui/MessageBubble";
import { m } from "#/paraglide/messages";
import { env } from "#/shared/config/env";
import { WaxSeal } from "#/shared/ui/WaxSeal";

export function ChatInterface() {
  const [input, setInput] = useState("");
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);
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

  const isStreaming = status === "submitted" || status === "streaming";
  const lastMsg = messages[messages.length - 1];

  function checkScrollPosition() {
    const container = scrollContainerRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    setShowJumpToLatest(distanceFromBottom > 100 && isStreaming);
  }

  // biome-ignore lint/correctness/useExhaustiveDependencies: messages triggers scroll; body uses stable ref
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distanceFromBottom < 100) {
      scrollRef.current?.scrollIntoView({ behavior: "smooth" });
    }
    checkScrollPosition();
  }, [messages]);

  useEffect(
    () => () => {
      stop();
    },
    [stop],
  );

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

  function handleScroll(e: UIEvent<HTMLDivElement>) {
    e.persist();
    checkScrollPosition();
  }

  function scrollToLatest() {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }

  return (
    <div className="flex flex-col h-full w-full max-w-4xl mx-auto border border-border/50 rounded-xl bg-background/60 backdrop-blur-sm overflow-hidden shadow-md">
      {error && (
        <Alert status="danger" className="m-3 rounded-lg shrink-0">
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
        onScroll={handleScroll}
        className="relative flex-1 overflow-y-auto p-4 sm:p-6 space-y-8"
      >
        {messages.length === 0 ? (
          <EmptyState onSelect={doSend} />
        ) : (
          messages.map((msg, index) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              isLast={index === messages.length - 1}
              isStreaming={isStreaming}
              onRegenerate={() => void regenerate()}
            />
          ))
        )}

        {isStreaming && lastMsg?.role === "user" && <StreamingIndicator />}

        <div ref={scrollRef} aria-hidden="true" />

        {showJumpToLatest && (
          <Button
            size="sm"
            variant="secondary"
            onPress={scrollToLatest}
            className="absolute bottom-4 left-1/2 -translate-x-1/2 shadow-md"
          >
            <ChevronDown size={14} aria-hidden="true" />
            Latest
          </Button>
        )}
      </div>

      {/* INPUT AREA */}
      <div className="p-3 sm:p-4 bg-surface border-t border-border/50 shrink-0">
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
            className="text-base resize-none rounded-lg bg-field-background text-field-foreground placeholder:text-field-placeholder focus-visible:ring-2 focus-visible:ring-accent/40"
            rows={2}
          />

          {isStreaming ? (
            <Button
              type="button"
              variant="danger"
              onPress={() => stop()}
              aria-label={m.chat_stop_button()}
              isIconOnly
              className="shrink-0 h-11 w-11"
            >
              <Square size={18} aria-hidden="true" />
            </Button>
          ) : (
            <Button
              type="submit"
              variant="primary"
              isDisabled={!input.trim()}
              aria-label={m.chat_send_button()}
              isIconOnly
              className="shrink-0 h-11 w-11"
            >
              <Send size={18} aria-hidden="true" />
            </Button>
          )}
        </form>
      </div>
    </div>
  );
}

function StreamingIndicator() {
  return (
    <div className="flex w-full gap-3">
      <WaxSeal icon={Scroll} size={28} aria-label="Assistant" />
      <div className="flex min-w-0 flex-col items-start">
        <span className="mb-1 font-display text-[10px] uppercase tracking-[0.12em] text-metal-foreground">
          {m.chat_role_assistant()}
        </span>
        <Card className="w-fit rounded-2xl rounded-tl-sm border border-border/50 bg-surface shadow-sm">
          <Card.Content className="flex items-center gap-3 px-4 py-3">
            <WaxSeal icon={Scroll} size={20} pulse aria-label="Scribing" />
            <span className="text-sm text-muted italic">Scribing a reply…</span>
          </Card.Content>
        </Card>
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
    <div className="h-full flex flex-col items-center justify-center text-center px-2 py-8">
      <WaxSeal
        icon={Scroll}
        size={64}
        className="mb-5"
        aria-label="The Archives are Open"
      />

      <h2 className="text-2xl sm:text-3xl font-display font-bold text-foreground mb-2 tracking-wide">
        {m.chat_empty_title()}
      </h2>
      <p className="max-w-md text-muted mb-8 text-base leading-relaxed">
        {m.chat_empty_description()}
      </p>

      <div className="w-full max-w-lg">
        <p className="text-[10px] font-display uppercase tracking-[0.12em] text-metal-foreground mb-3">
          {m.chat_example_prompt()}
        </p>
        <div className="flex flex-col gap-3">
          {examples.map((query) => (
            <button
              key={query}
              type="button"
              onClick={() => onSelect(query)}
              className="text-left rounded-lg border border-metal/30 bg-surface p-3 transition-colors hover:bg-surface-secondary hover:border-metal/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
            >
              <p className="text-sm text-foreground leading-snug">{query}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
