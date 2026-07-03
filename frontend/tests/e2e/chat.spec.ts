import { expect, test } from "@playwright/test";
import { ChatMother, FEAR_REPLY } from "../../src/test/mothers/chat.mother";

// Derive the intercepted SSE body from the same factory used by unit tests.
// This ensures the e2e scenario stays in sync with the unit-level fixture.
const STREAM_BODY = ChatMother.sseStream(FEAR_REPLY);
const USER_QUESTION = "How does Fear work?";

test.describe("Chat happy path", () => {
  test.beforeEach(async ({ page }) => {
    // Intercept the backend with a v6 UI Message Stream response
    await page.route("**/chat/", async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "x-vercel-ai-ui-message-stream": "v1",
          "Cache-Control": "no-cache",
        },
        body: STREAM_BODY,
      });
    });

    await page.goto("/");
  });

  test("sends a message and renders streamed assistant reply", async ({
    page,
  }) => {
    await page.getByRole("textbox").fill(USER_QUESTION);
    await page.getByRole("button", { name: "Send" }).click();

    // User bubble appears immediately
    await expect(page.getByText(USER_QUESTION)).toBeVisible();

    // Streamed reply assembles (words arrive incrementally)
    await expect(page.getByText(/Fear forces the enemy unit/)).toBeVisible({
      timeout: 5_000,
    });

    // After stream: Regenerate button appears on the assistant message
    await expect(
      page.getByRole("button", { name: "Regenerate" }),
    ).toBeVisible();
  });

  test("empty state shown on first load with example queries", async ({
    page,
  }) => {
    await expect(page.getByText("The Archives are Open")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /What happens when a unit/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Tell me about the Blood Knights/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /How does Fear work\?/ }),
    ).toBeVisible();
  });

  test("clicking an example query sends it and renders the reply", async ({
    page,
  }) => {
    await page
      .getByRole("button", { name: /How does Fear work\?/ })
      .click();

    await expect(page.getByText(USER_QUESTION)).toBeVisible();
    await expect(page.getByText(/Fear forces the enemy unit/)).toBeVisible({
      timeout: 5_000,
    });
  });

  test("Send button disabled when input is empty", async ({ page }) => {
    await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});

test.describe("Chat sources rendering", () => {
  const SOURCES = [
    {
      id: "fear",
      label: "SpecialRule",
      text: "Fear forces the enemy unit to take a Panic test.",
    },
    {
      id: "flaming-attacks",
      label: "SpecialRule",
      text: "Flaming Attacks cause Fear tests for Regeneration.",
    },
  ];

  test("renders source chips after the assistant reply", async ({ page }) => {
    await page.route("**/chat/", async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "x-vercel-ai-ui-message-stream": "v1",
          "Cache-Control": "no-cache",
        },
        body: ChatMother.sseStream(FEAR_REPLY, { sources: SOURCES }),
      });
    });

    await page.goto("/");
    await page.getByRole("textbox").fill(USER_QUESTION);
    await page.getByRole("button", { name: "Send" }).click();

    await expect(page.getByText(/Fear forces the enemy unit/)).toBeVisible({
      timeout: 5_000,
    });
    await expect(page.getByText("Sources")).toBeVisible();
    await expect(page.getByRole("button", { name: "fear" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "flaming-attacks" }),
    ).toBeVisible();
  });
});

test.describe("Chat stop flow", () => {
  test("stop button ends streaming and returns to idle UI", async ({
    page,
  }) => {
    // Delay the response so the stream remains active long enough for Stop to appear
    await page.route("**/chat/", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 5_000));
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "x-vercel-ai-ui-message-stream": "v1",
          "Cache-Control": "no-cache",
        },
        body: STREAM_BODY,
      });
    });

    await page.goto("/");
    await page.getByRole("textbox").fill(USER_QUESTION);
    await page.getByRole("button", { name: "Send" }).click();

    await expect(page.getByRole("button", { name: "Stop" })).toBeVisible({
      timeout: 5_000,
    });

    await page.getByRole("button", { name: "Stop" }).click();

    // After stopping, the idle UI returns: Send button replaces Stop button
    await expect(page.getByRole("button", { name: "Send" })).toBeVisible({
      timeout: 5_000,
    });
  });
});
