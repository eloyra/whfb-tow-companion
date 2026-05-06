import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// vi.mock calls are hoisted — safe to reference mocked modules below
vi.mock("@ai-sdk/react", () => ({ useChat: vi.fn() }));
vi.mock("ai", () => ({
  DefaultChatTransport: vi.fn().mockImplementation(() => ({})),
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
    sendMessage: vi.fn().mockResolvedValue(undefined),
    status: "ready" as ChatStatus,
    error: undefined,
    stop: vi.fn(),
    regenerate: vi.fn().mockResolvedValue(undefined),
    clearError: vi.fn(),
    id: "test-chat",
    setMessages: vi.fn(),
    resumeStream: vi.fn(),
    addToolResult: vi.fn(),
    addToolOutput: vi.fn(),
    addToolApprovalResponse: vi.fn(),
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
    const sendMessage = vi.fn().mockResolvedValue(undefined);
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
    const clearError = vi.fn();
    const regenerate = vi.fn().mockResolvedValue(undefined);
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
    // exactly one Regenerate button — on the last assistant message
    const btns = screen.getAllByRole("button", { name: "Regenerate" });
    expect(btns).toHaveLength(1);
  });
});
