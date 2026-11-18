import { expect, test } from "@playwright/test";

import { expectAccessible } from "./helpers";

// A first-time visitor: nothing stored yet, so the tour opens by itself on the seeded demo.
test.use({ storageState: { cookies: [], origins: [] } });

test("tour: a first visit is walked through the screens, and it does not come back", async ({ page }) => {
  await page.goto("/app/");
  const tour = page.getByRole("dialog");
  await expect(tour.getByRole("heading", { name: "Welcome to GivemeaChance" })).toBeVisible();
  await expectAccessible(page);

  await tour.getByRole("button", { name: "Take the tour" }).click();
  const stops = [
    ["Decide in seconds", /\/discover$/],
    ["Every job, ranked", /\/jobs$/],
    ["Why it fits", /\/jobs\/\d+$/],
    ["A résumé for this job", /\/jobs\/\d+$/],
    ["Track every application", /\/applications$/],
    ["Start from any résumé", /\/onboarding\?step=background$/],
    ["One reviewed profile", /\/profile$/],
    ["Fill the gaps", /\/profile$/],
  ] as const;
  const viewport = page.viewportSize() ?? { width: 0, height: 0 };
  for (const [title, url] of stops) {
    await expect(tour.getByRole("heading", { name: title })).toBeVisible();
    await expect(page).toHaveURL(url);
    // The spotlight has found its element and the whole card is on screen.
    const spot = page.locator(".tour-spot");
    await expect(spot).not.toHaveClass(/tour-spot-off/);
    await expect
      .poll(async () => {
        const box = await page.locator(".tour-card").boundingBox();
        return box !== null && box.y >= 0 && box.y + box.height <= viewport.height && box.x >= 0;
      })
      .toBe(true);
    if (title === "Why it fits" || title === "Start from any résumé") await expectAccessible(page);
    await tour.getByRole("button", { name: "Next" }).click();
  }
  await expect(tour.getByRole("heading", { name: "That is the tour" })).toBeVisible();
  await tour.getByRole("button", { name: "Done" }).click();
  await expect(tour).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("article").first()).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  // The banner starts it again on request.
  await page.getByRole("button", { name: "Take the tour" }).click();
  await expect(
    page.getByRole("dialog").getByRole("heading", { name: "Welcome to GivemeaChance" }),
  ).toBeVisible();
});
