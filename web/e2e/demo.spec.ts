import { expect, test } from "@playwright/test";

import { expectAccessible } from "./helpers";

// Runs against the seeded, read-only DEMO_MODE server (see playwright.config.ts).
test("demo: sample workspace opens without signing in and refuses every change", async ({ page }) => {
  await page.goto("/app/");
  await expect(page.getByRole("status").filter({ hasText: "Read-only demo" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toHaveCount(0);

  // The app opens on the Discover deck with the best seeded match
  await expect(page.getByRole("article").first()).toBeVisible();
  await expectAccessible(page);

  // Seeded jobs with match scores
  await page.getByRole("link", { name: "Jobs" }).first().click();
  const jobLinks = page.getByRole("main").getByRole("listitem").getByRole("link");
  await expect(jobLinks.first()).toBeVisible();
  expect(await jobLinks.count()).toBeGreaterThanOrEqual(8);
  await expectAccessible(page);

  // A job with generated documents
  await jobLinks.first().click();
  await expect(page.getByRole("heading", { name: "Why it fits" })).toBeVisible();
  await expectAccessible(page);

  // The board is filled across columns
  await page.getByRole("link", { name: "Applications" }).first().click();
  const column = (name: string) => page.getByRole("region", { name });
  const cards = (name: string) => column(name).getByRole("button", { name: /^Drag / });
  await expect(cards("Applied")).toHaveCount(1);
  await expect(cards("Interview")).toHaveCount(1);
  await expectAccessible(page);

  // Any change is refused with a friendly message
  await column("Applied").getByRole("combobox").selectOption("offer");
  await expect(page.getByText(/read-only demo, so changes are turned off/i)).toBeVisible();
  await expect(cards("Applied")).toHaveCount(1);
});

test("demo: the API refuses writes with code 1004 and signing in is closed", async ({ request }) => {
  for (const [method, path] of [
    ["POST", "/api/v1/searches"],
    ["POST", "/api/v1/session"],
    ["POST", "/api/v1/account"],
    ["PATCH", "/api/v1/profile"],
  ] as const) {
    const response = await request.fetch(path, { method, data: {} });
    expect(response.status(), `${method} ${path}`).toBe(403);
    expect((await response.json()).error_code).toBe(1004);
  }
});
