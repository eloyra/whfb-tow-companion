import type { UIMessage } from "ai";

// ── primitives ────────────────────────────────────────────────────────────────

function userMsg(text: string): UIMessage {
  return {
    id: `user-${text.slice(0, 24).replace(/\s/g, "-")}`,
    role: "user",
    parts: [{ type: "text", text }],
  };
}

function assistantMsg(text: string): UIMessage {
  return {
    id: `assistant-${text.slice(0, 24).replace(/\s/g, "-")}`,
    role: "assistant",
    parts: [{ type: "text", text }],
  };
}

// ── ChatMother ────────────────────────────────────────────────────────────────
//
// Domain-specific named scenarios for WHFB test fixtures.
// Prefer these over inline { id, role, parts } literals in tests — they make
// intent clear and centralise the UIMessage shape in one place.

export const ChatMother = {
  /** A single user question. */
  userMessage: (text = "How does Fear work?") => userMsg(text),

  /** A single assistant reply. */
  assistantMessage: (
    text = "Fear forces the enemy unit to take a Panic test.",
  ) => assistantMsg(text),

  /**
   * Short rules Q&A — the canonical "does the chat render text?" scenario.
   * Used by unit tests that just need any non-empty conversation.
   */
  fearRulesExchange: (): UIMessage[] => [
    userMsg("How does Fear work?"),
    assistantMsg("Fear forces the enemy unit to take a Panic test."),
  ],

  /**
   * Assistant reply containing a GFM markdown table.
   * Use this to verify react-markdown + remark-gfm renders tables correctly.
   */
  unitStatsExchange: (): UIMessage[] => [
    userMsg("Show me the Skeleton Warriors stat profile."),
    assistantMsg(
      [
        "| M | WS | BS | S | T | W | I | A | Ld |",
        "|---|----|----|---|---|---|---|---|-----|",
        "| 4 |  2 |  2 | 3 | 3 | 1 | 2 | 1 |  3 |",
        "",
        "Skeleton Warriors are the core infantry of **Tomb Kings** armies.",
      ].join("\n"),
    ),
  ],

  /**
   * Multi-turn conversation.
   * Use this to verify Regenerate appears only on the last assistant message.
   */
  multiTurnConversation: (): UIMessage[] => [
    userMsg("What is the difference between Panic and Terror?"),
    assistantMsg(
      "**Panic** triggers when a friendly unit nearby breaks or is destroyed. " +
        "**Terror** is caused by monstrous creatures and requires a Terror test.",
    ),
    userMsg("Which units cause Terror?"),
    assistantMsg(
      "Units with the Terror special rule — typically large monsters and daemons " +
        "such as Dragons, Giants, and Greater Daemons.",
    ),
  ],

  /**
   * A conversation that has reached an error state.
   * Returns both messages and a pre-constructed Error for convenience.
   */
  errorState: () => ({
    messages: [userMsg("What army should I play?")],
    error: new Error("LLM provider unavailable"),
  }),

  /**
   * Produces the raw SSE body for the Playwright network interceptor,
   * matching a given assistant reply text (v6 UI Message Stream format).
   */
  sseStream: (text: string, id = "msg_test"): string =>
    [
      `data: {"type":"text-start","id":"${id}"}`,
      ...text
        .split(" ")
        .map(
          (word) =>
            `data: {"type":"text-delta","id":"${id}","delta":"${word} "}`,
        ),
      `data: {"type":"text-end","id":"${id}"}`,
      `data: {"type":"finish-step"}`,
    ]
      .map((line) => `${line}\n\n`)
      .join(""),
};

/** The assistant reply text used by fearRulesExchange — re-exported so
 *  Playwright assertions can match against the exact same string. */
export const FEAR_REPLY = "Fear forces the enemy unit to take a Panic test.";
