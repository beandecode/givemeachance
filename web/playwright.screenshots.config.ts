import { defineConfig, devices } from "@playwright/test";

const PORT = 5097;

/** README screenshots: `npm run screenshots` drives the seeded read-only demo and writes ../docs/images/*.png. */
export default defineConfig({
  testDir: "e2e/screenshots",
  workers: 1,
  timeout: 60_000,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${String(PORT)}`,
    // Screenshots show the app, not the first-visit tour.
    storageState: {
      cookies: [],
      origins: [
        {
          origin: `http://127.0.0.1:${String(PORT)}`,
          localStorage: [{ name: "gmc.tour.v2", value: "done" }],
        },
      ],
    },
  },
  webServer: {
    command: `python ../scripts/e2e_web_server.py ${String(PORT)} --demo`,
    url: `http://127.0.0.1:${String(PORT)}/readyz`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
});
