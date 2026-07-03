import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// vi.mock calls are hoisted — safe to reference mocked modules below
vi.mock("@ai-sdk/react", () => ({ useChat: vi.fn(function () {}) }));
vi.mock("ai", () => ({
  DefaultChatTransport: vi.fn(function () {
    return {};
  }),
}));
vi.mock("#/shared/config/env", () => ({
  env: { apiUrl: "http://localhost:8000" },
}));

import { useChat } from "@ai-sdk/react";
import type { UIMessage } from "ai";
import { ChatMother } from "#/test/mothers/chat.mother";
import { ChatInterface } from "./ChatInterface";

const mockUseChat = vi.mocked(useChat);

// ── useChat stub factory ───────────────────────────────────────────────────────

type ChatStatus = "submitted" | "streaming" | "ready" | "error";

function useChatStub(
  overrides: {
    messages?: UIMessage[];
    status?: ChatStatus;
    error?: Error;
    sendMessage?: ReturnType<typeof vi.fn>;
    stop?: ReturnType<typeof vi.fn>;
    regenerate?: ReturnType<typeof vi.fn>;
    clearError?: ReturnType<typeof vi.fn>;
  } = {},
) {
  return {
    messages: [],
    sendMessage: vi.fn(function () {}).mockResolvedValue(undefined),
    status: "ready" as ChatStatus,
    error: undefined,
    stop: vi.fn(function () {}),
    regenerate: vi.fn(function () {}).mockResolvedValue(undefined),
    clearError: vi.fn(function () {}),
    id: "test-chat",
    setMessages: vi.fn(function () {}),
    resumeStream: vi.fn(function () {}),
    addToolResult: vi.fn(function () {}),
    addToolOutput: vi.fn(function () {}),
    addToolApprovalResponse: vi.fn(function () {}),
    ...overrides,
    // biome-ignore lint/suspicious/noExplicitAny: test mock — exact UseChatHelpers shape not needed
  } as any;
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe("ChatInterface", () => {
  it("shows empty state when no messages", () => {
    mockUseChat.mockReturnValue(useChatStub());
    render(<ChatInterface />);
    expect(screen.getByText("The Archives are Open")).toBeInTheDocument();
  });

  it("renders user and assistant bubbles (fear rules exchange)", () => {
    mockUseChat.mockReturnValue(
      useChatStub({ messages: ChatMother.fearRulesExchange() }),
    );
    render(<ChatInterface />);
    expect(screen.getByText("How does Fear work?")).toBeInTheDocument();
    expect(screen.getByText(/Fear forces the enemy unit/)).toBeInTheDocument();
  });

  it("renders GFM markdown table from unit stats exchange", () => {
    mockUseChat.mockReturnValue(
      useChatStub({ messages: ChatMother.unitStatsExchange() }),
    );
    render(<ChatInterface />);
    // remark-gfm renders the table — check for a cell value
    expect(screen.getByText("Tomb Kings")).toBeInTheDocument();
  });

  it("shows Stop button while streaming", () => {
    mockUseChat.mockReturnValue(
      useChatStub({
        messages: [ChatMother.userMessage()],
        status: "streaming",
      }),
    );
    render(<ChatInterface />);
    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
  });

  it("Send button disabled when input is empty", () => {
    mockUseChat.mockReturnValue(useChatStub());
    render(<ChatInterface />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("Send button enabled after typing", () => {
    mockUseChat.mockReturnValue(useChatStub());
    render(<ChatInterface />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "Hello" },
    });
    expect(screen.getByRole("button", { name: "Send" })).not.toBeDisabled();
  });

  it("calls sendMessage with input text on form submit", () => {
    const sendMessage = vi.fn(function () {}).mockResolvedValue(undefined);
    mockUseChat.mockReturnValue(useChatStub({ sendMessage }));
    render(<ChatInterface />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "Fear question" },
    });
    // biome-ignore lint/style/noNonNullAssertion: form always present in this render
    fireEvent.submit(screen.getByRole("textbox").closest("form")!);

    expect(sendMessage).toHaveBeenCalledWith({ text: "Fear question" });
  });

  it("shows error banner and calls clearError+regenerate on Retry", () => {
    const clearError = vi.fn(function () {});
    const regenerate = vi.fn(function () {}).mockResolvedValue(undefined);
    const { messages, error } = ChatMother.errorState();
    mockUseChat.mockReturnValue(
      useChatStub({ messages, error, clearError, regenerate }),
    );
    render(<ChatInterface />);

    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("LLM provider unavailable")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(clearError).toHaveBeenCalled();
    expect(regenerate).toHaveBeenCalled();
  });

  it("Regenerate appears only on last assistant message (multi-turn)", () => {
    mockUseChat.mockReturnValue(
      useChatStub({ messages: ChatMother.multiTurnConversation() }),
    );
    render(<ChatInterface />);
    const btns = screen.getAllByRole("button", { name: "Regenerate" });
    expect(btns).toHaveLength(1);
  });

  it("calls stop when Stop button is clicked", () => {
    const stop = vi.fn();
    mockUseChat.mockReturnValue(
      useChatStub({
        messages: [ChatMother.userMessage()],
        status: "streaming",
        stop,
      }),
    );
    render(<ChatInterface />);
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(stop).toHaveBeenCalled();
  });

  it("calls regenerate when Regenerate button is clicked", () => {
    const regenerate = vi.fn().mockResolvedValue(undefined);
    mockUseChat.mockReturnValue(
      useChatStub({ messages: ChatMother.fearRulesExchange(), regenerate }),
    );
    render(<ChatInterface />);
    fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    expect(regenerate).toHaveBeenCalled();
  });

  it("shows streaming indicator when streaming and last message is user", () => {
    mockUseChat.mockReturnValue(
      useChatStub({
        messages: [ChatMother.userMessage()],
        status: "streaming",
      }),
    );
    const { container } = render(<ChatInterface />);
    const dots = container.querySelector(".animate-bounce");
    expect(dots).toBeInTheDocument();
  });

  it("renders data-sources parts as source chips", () => {
    const messages: UIMessage[] = [
      ChatMother.userMessage("How does Fear work?"),
      {
        id: "assistant-sources",
        role: "assistant",
        parts: [
          { type: "text", text: "Fear forces a Panic test." },
          {
            type: "data-sources",
            id: "src-1",
            data: [
              {
                id: "fear",
                label: "SpecialRule",
                text: "Fear forces the enemy unit to take a Panic test.",
              },
            ],
          },
        ],
      },
    ];

    mockUseChat.mockReturnValue(useChatStub({ messages }));
    render(<ChatInterface />);

    expect(screen.getByText("Sources")).toBeInTheDocument();
    expect(screen.getByText("fear")).toBeInTheDocument();
  });

  it("drops malformed data-sources parts without crashing", () => {
    const messages: UIMessage[] = [
      ChatMother.userMessage("How does Fear work?"),
      {
        id: "assistant-bad-sources",
        role: "assistant",
        parts: [
          { type: "text", text: "Fear forces a Panic test." },
          {
            type: "data-sources",
            id: "src-2",
            // Missing required `id` field inside the data array.
            data: [{ text: "Missing id" }],
          },
        ],
      },
    ];

    mockUseChat.mockReturnValue(useChatStub({ messages }));
    render(<ChatInterface />);

    // The text still renders.
    expect(screen.getByText("Fear forces a Panic test.")).toBeInTheDocument();
    // The malformed source is dropped silently.
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
  });

  it("renders 'no sources retrieved' when data-sources payload is empty", () => {
    const messages: UIMessage[] = [
      ChatMother.userMessage("How does Fear work?"),
      {
        id: "assistant-empty-sources",
        role: "assistant",
        parts: [
          { type: "text", text: "Fear forces a Panic test." },
          {
            type: "data-sources",
            id: "src-3",
            data: [],
          },
        ],
      },
    ];

    mockUseChat.mockReturnValue(useChatStub({ messages }));
    render(<ChatInterface />);

    expect(screen.getByText("Sources")).toBeInTheDocument();
    expect(screen.getByText("No sources retrieved")).toBeInTheDocument();
  });
});
