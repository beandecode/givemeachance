import { defineConfig, devices } from "@playwright/test";

const PORT = 5099;
const DEMO_PORT = 5098;
const DEMO_URL = `http://127.0.0.1:${String(DEMO_PORT)}`;
// Tests browse as a returning visitor; tour.spec clears this to see the first-visit tour.
const TOUR_SEEN = [{ name: "gmc.tour.v2", value: "done" }];

/** Browser tests against the built app (app/spa_dist) served by a throwaway mock-provider Flask server. */
export default defineConfig({
  testDir: "e2e",
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${String(PORT)}`,
    trace: "retain-on-failure",
    storageState: {
      cookies: [],
      origins: [
        { origin: `http://127.0.0.1:${String(PORT)}`, localStorage: TOUR_SEEN },
        { origin: DEMO_URL, localStorage: TOUR_SEEN },
      ],
    },
  },
  webServer: [
    {
      command: `python ../scripts/e2e_web_server.py ${String(PORT)}`,
      url: `http://127.0.0.1:${String(PORT)}/readyz`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { MOCK_LLM_DELAY_SECONDS: "2" },
    },
    {
      // Read-only demo: seeded sample workspace, every write refused (code 1004).
      command: `python ../scripts/e2e_web_server.py ${String(DEMO_PORT)} --demo`,
      url: `http://127.0.0.1:${String(DEMO_PORT)}/readyz`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"] },
      testIgnore: /(phone|demo|tour|layout|a11y-dark)\.spec|screenshots\//,
    },
    // Everything below browses the seeded read-only demo, where each screen has content, at other sizes.
    {
      name: "demo",
      use: { ...devices["Desktop Chrome"], baseURL: DEMO_URL },
      testMatch: /(demo|tour|layout|a11y-dark)\.spec/,
    },
    {
      name: "demo-phone",
      use: { ...devices["Pixel 7"], baseURL: DEMO_URL },
      testMatch: /(tour|layout|a11y-dark|phone)\.spec/,
    },
    {
      name: "tablet",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 768, height: 1024 },
        hasTouch: true,
        baseURL: DEMO_URL,
      },
      // Layout depends on the width; colours do not, so dark mode is checked on desktop and phone only.
      testMatch: /layout\.spec/,
    },
    {
      name: "desktop-wide",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 }, baseURL: DEMO_URL },
      testMatch: /layout\.spec/,
    },
  ],
});
