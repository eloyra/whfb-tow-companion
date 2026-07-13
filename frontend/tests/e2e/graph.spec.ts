import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// Fixtures mirror the backend's /graph/nodes and /graph/subgraph/{id} response
// shapes (backend/api/routes/graph.py). "fear" is used as the stable seed
// node, matching the special rule that exists in the real graph.
const NODES_FEAR = [
  {
    id: "fear",
    label: "SpecialRule",
    name: "Fear",
    source_url: "https://tow.whfb.app/special-rules/fear",
  },
];

const SUBGRAPH_FEAR = {
  nodes: [
    {
      id: "fear",
      label: "SpecialRule",
      name: "Fear",
      source_url: "https://tow.whfb.app/special-rules/fear",
    },
    {
      id: "terror",
      label: "SpecialRule",
      name: "Terror",
      source_url: "https://tow.whfb.app/special-rules/terror",
    },
    {
      id: "ghoul-king",
      label: "Unit",
      name: "Ghoul King",
      source_url: "https://tow.whfb.app/unit/ghoul-king",
    },
  ],
  edges: [
    { source: "fear", target: "terror", rel_type: "REFERENCES" },
    { source: "ghoul-king", target: "fear", rel_type: "HAS_RULE" },
  ],
};

async function mockGraphBackend(page: import("@playwright/test").Page) {
  await page.route("**/graph/nodes**", async (route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const nodes = q && "fear".includes(q) ? NODES_FEAR : [];
    await route.fulfill({ status: 200, json: { nodes } });
  });

  await page.route("**/graph/subgraph/**", async (route) => {
    await route.fulfill({ status: 200, json: SUBGRAPH_FEAR });
  });
}

test.describe("Graph viewer", () => {
  test.beforeEach(async ({ page }) => {
    await mockGraphBackend(page);
    await page.goto("/graph");
  });

  test("shows an empty state before any node is selected", async ({ page }) => {
    await expect(
      page.getByText(/Search for a rule, unit, or spell/i),
    ).toBeVisible();
  });

  test("searches for a known node, selects it, and renders its neighborhood", async ({
    page,
  }) => {
    await page.getByPlaceholder(/Search rules, units, spells/i).fill("fear");

    const result = page.getByRole("button", { name: /Fear/ }).first();
    await expect(result).toBeVisible();
    await result.click();

    // At least one node renders. Position is a computed radial layout
    // (deterministic, but not asserted here — see layout.test.ts for that).
    await expect(page.locator(".react-flow__node").first()).toBeVisible();
    const nodeCount = await page.locator(".react-flow__node").count();
    expect(nodeCount).toBeGreaterThan(0);
  });

  test("clicking a neighbor node re-centers the graph", async ({ page }) => {
    await page.getByPlaceholder(/Search rules, units, spells/i).fill("fear");
    await page.getByRole("button", { name: /Fear/ }).first().click();
    await expect(page.locator(".react-flow__node").first()).toBeVisible();

    // Re-route the subgraph endpoint so clicking a neighbor visibly re-centers
    // (a distinct payload proves the re-fetch, not just the same data twice).
    await page.unroute("**/graph/subgraph/**");
    await page.route("**/graph/subgraph/**", async (route) => {
      await route.fulfill({
        status: 200,
        json: {
          nodes: [
            {
              id: "terror",
              label: "SpecialRule",
              name: "Terror",
              source_url: "https://tow.whfb.app/special-rules/terror",
            },
          ],
          edges: [],
        },
      });
    });

    const terrorNode = page.locator(".react-flow__node", { hasText: "Terror" });
    await terrorNode.click();

    // Re-centering on "terror" (no neighbors in the re-routed fixture) leaves
    // exactly one node on screen.
    await expect(page.locator(".react-flow__node")).toHaveCount(1);
    await expect(page.locator(".react-flow__node", { hasText: "Terror" })).toBeVisible();
  });

  test("shows no matching results for an unknown query", async ({ page }) => {
    await page.getByPlaceholder(/Search rules, units, spells/i).fill("xyzzy-not-a-real-rule");

    await expect(page.getByText(/No matching nodes found/i)).toBeVisible();
  });
});

test.describe("Graph viewer accessibility", () => {
  test("empty graph viewer has no detectable a11y violations", async ({ page }) => {
    await mockGraphBackend(page);
    await page.goto("/graph");
    await expect(
      page.getByText(/Search for a rule, unit, or spell/i),
    ).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test("populated graph viewer has no detectable a11y violations", async ({ page }) => {
    await mockGraphBackend(page);
    await page.goto("/graph");

    await page.getByPlaceholder(/Search rules, units, spells/i).fill("fear");
    await page.getByRole("button", { name: /Fear/ }).first().click();
    await expect(page.locator(".react-flow__node").first()).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
});
