import { useChat } from "@ai-sdk/react";
import { Button, Card, Input } from "@heroui/react";
import { DefaultChatTransport } from "ai";
import type * as React from "react";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

export function ChatInterface() {
  const [input, setInput] = useState("");

  const { messages, sendMessage } = useChat({
    transport: new DefaultChatTransport({
      api: `${import.meta.env.VITE_API_URL || "http://localhost:8000"}/chat`,
    }),
    onError: (error) => console.error("Chat API Error:", error),
  });

  useEffect(() => {
    console.info("Chat Messages", messages);
  }, [messages]);

  const onSubmit = (e: React.SubmitEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    sendMessage({
      text: input,
    }).catch((error) => console.error("Error sending message:", error));
    setInput("");
  };

  const isLoading =
    messages.length > 0 && messages[messages.length - 1].role === "user";

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] w-full max-w-4xl mx-auto border border-border/50 rounded-xl bg-background/50 backdrop-blur-sm overflow-hidden shadow-lg">
      {/* --- MESSAGE HISTORY AREA --- */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center opacity-50">
            <span className="text-4xl mb-4">📜</span>
            <h3 className="text-xl font-display font-bold">
              The Archives are Open
            </h3>
            <p className="max-w-md">
              Ask a question about unit stats, army compositions, or the lore of
              the Old World.
            </p>
          </div>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={`flex w-full ${
                m.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <Card
                className={`max-w-[80%] ${
                  m.role === "user" ? "bg-primary text-primary-foreground" : ""
                }`}
              >
                <Card.Content className="py-3 px-4">
                  {m.parts.map((part, index) =>
                    part.type === "text" ? (
                      <div
                        // biome-ignore lint/suspicious/noArrayIndexKey: can't be sorted or filtered
                        key={index}
                        className="prose prose-sm dark:prose-invert max-w-none"
                      >
                        <ReactMarkdown>{part.text}</ReactMarkdown>
                      </div>
                    ) : null,
                  )}
                </Card.Content>
              </Card>
            </div>
          ))
        )}

        {isLoading && (
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
      </div>

      {/* --- INPUT AREA --- */}
      <div className="p-4 bg-content1 border-t border-border/50">
        <form onSubmit={onSubmit} className="flex gap-2 items-center">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Query the Grand Theogonist..."
            fullWidth
            variant="primary"
            disabled={isLoading}
            className="text-base"
          />

          <Button
            type="submit"
            variant="primary"
            isDisabled={!input.trim() || isLoading}
          >
            {isLoading ? "..." : "Send"}
          </Button>
        </form>
      </div>
    </div>
  );
}
