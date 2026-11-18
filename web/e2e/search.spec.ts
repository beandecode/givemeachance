import { expect, test } from "@playwright/test";

import { expectAccessible } from "./helpers";
import { seedProfile, total } from "./seed";

test("Search sheet: choose to only add the jobs, then they wait unscored", async ({ page }) => {
  await seedProfile(page);
  await page.goto("/app/jobs");
  await page.getByRole("button", { name: "Search options" }).click();

  const sheet = page.getByRole("dialog", { name: "Search the job board" });
  await expect(sheet.getByLabel("Keywords")).toBeVisible();
  await expect(sheet.getByText("Sample data: no job-board or AI quota is used.")).toBeVisible();
  await expectAccessible(page);

  await sheet.getByRole("radio", { name: "Only add them, I will score later" }).check();
  await sheet.getByRole("button", { name: "Search" }).click();

  await expect(page.getByText(/^Found \d+ new jobs?$/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/not scored yet/)).toBeVisible();
  const added = await total(page, "pending");
  expect(added).toBeGreaterThanOrEqual(2);
  const unscored = (await (await page.request.get("/api/v1/jobs?scored=false&limit=100")).json()) as {
    data: { total: number };
  };
  expect(unscored.data.total).toBe(added);

  // The Not scored view lists them; one can be scored on its own, the rest all at once
  await page.goto("/app/jobs?view=unscored");
  const rows = page.getByRole("main").getByRole("listitem");
  await expect(rows).toHaveCount(added);
  await expectAccessible(page);
  await rows
    .first()
    .getByRole("button", { name: /^Score / })
    .click();
  await expect(rows).toHaveCount(added - 1, { timeout: 60_000 });
  await page.getByRole("button", { name: /^Score all \d+$/ }).click();
  await expect(page.getByText("Every job is scored")).toBeVisible({ timeout: 60_000 });
  const left = (await (await page.request.get("/api/v1/jobs?scored=false&limit=100")).json()) as {
    data: { total: number };
  };
  expect(left.data.total).toBe(0);
});

test("Search sheet: the one-click button still searches and scores everything", async ({ page }) => {
  await seedProfile(page);
  await page.goto("/app/jobs");
  await page.getByRole("button", { name: "Search job board" }).click();

  await expect(page.getByText(/^Found \d+ new jobs?$/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/\d+ scored/)).toBeVisible();
  const unscored = (await (await page.request.get("/api/v1/jobs?scored=false&limit=100")).json()) as {
    data: { total: number };
  };
  expect(unscored.data.total).toBe(0);
});
