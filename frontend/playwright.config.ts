import { defineConfig, devices } from "@playwright/test";

// Override with APP_URL to point at a running server (skips dev-server startup).
// Example: APP_URL=http://staging.example.com pnpm exec playwright test
const APP_URL = process.env.APP_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: APP_URL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Only auto-start the dev server when APP_URL is not provided.
  webServer: process.env.APP_URL
    ? undefined
    : {
        command: "pnpm dev",
        url: "http://localhost:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
