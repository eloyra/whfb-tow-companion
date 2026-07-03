import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { ChatMother, FEAR_REPLY } from "#/test/mothers/chat.mother.ts";

const STREAM_BODY = ChatMother.sseStream(FEAR_REPLY);

test.describe("Accessibility", () => {
  test("empty chat interface has no detectable a11y violations", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByText("The Archives are Open")).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test("chat with messages has no detectable a11y violations", async ({
    page,
  }) => {
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
    await page.getByRole("textbox").fill("How does Fear work?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(
      page.getByRole("button", { name: "Regenerate" }),
    ).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test("chat with sources has no detectable a11y violations", async ({
    page,
  }) => {
    await page.route("**/chat/", async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "x-vercel-ai-ui-message-stream": "v1",
          "Cache-Control": "no-cache",
        },
        body: ChatMother.sseStream(FEAR_REPLY, {
          sources: [
            {
              id: "fear",
              label: "SpecialRule",
              text: "Fear forces the enemy unit to take a Panic test.",
            },
          ],
        }),
      });
    });

    await page.goto("/");
    await page.getByRole("textbox").fill("How does Fear work?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText("Sources")).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
});
