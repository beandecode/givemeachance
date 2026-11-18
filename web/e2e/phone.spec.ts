import { expect, test } from "@playwright/test";

// Phone-only interactions on the seeded demo (every screen has content there).
test("jobs: filters open as a sheet, narrow the list and close again", async ({ page }) => {
  await page.goto("/app/jobs");
  const rows = page.getByRole("main").getByRole("listitem");
  await expect(rows.first()).toBeVisible();
  const before = await rows.count();

  await page.getByRole("button", { name: "Filters" }).click();
  const sheet = page.getByRole("dialog", { name: "Filters" });
  await expect(sheet).toBeVisible();
  await sheet.getByLabel("Status").selectOption({ label: "Rejected" });
  await sheet.getByRole("button", { name: "Close" }).click();
  await expect(sheet).toBeHidden();

  await expect(page.getByRole("button", { name: "Filters (1)" })).toBeVisible();
  await expect
    .poll(async () => {
      const count = await rows.count();
      return count > 0 && count < before;
    })
    .toBe(true);
});

test("job: the next step and the tab bar are one block with no gap", async ({ page }) => {
  await page.goto("/app/jobs");
  // A saved job has a match but no documents yet, so the bar offers to write the résumé.
  await page
    .getByRole("main")
    .getByRole("listitem")
    .filter({ hasText: "Saved" })
    .getByRole("link")
    .first()
    .click();
  const bar = page.getByRole("region", { name: "Next step" });
  await expect(bar).toBeVisible();

  const barBox = await bar.boundingBox();
  const tabBox = await page.getByRole("navigation", { name: "Main" }).last().boundingBox();
  const dockBox = await page.locator("#bottom-dock").boundingBox();
  if (!barBox || !tabBox || !dockBox) throw new Error("dock not laid out");
  // The bar ends exactly where the tab bar starts, and both share the dock's width.
  expect(Math.abs(barBox.y + barBox.height - tabBox.y)).toBeLessThanOrEqual(0.5);
  expect(Math.abs(barBox.x - tabBox.x)).toBeLessThanOrEqual(0.5);
  expect(Math.abs(barBox.width - tabBox.width)).toBeLessThanOrEqual(0.5);

  // Nothing from the page shows at the seam, at the edges or in the middle.
  const hits = await page.evaluate(
    ({ seam, width }) => {
      const dock = document.getElementById("bottom-dock");
      return [2, width / 2, width - 2].flatMap((x) =>
        [seam - 0.5, seam + 0.5].map((y) => dock?.contains(document.elementFromPoint(x, y)) ?? false),
      );
    },
    { seam: tabBox.y, width: dockBox.width },
  );
  expect(hits).toEqual([true, true, true, true, true, true]);

  // The end of the page can be scrolled clear of the dock.
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  const clear = await page.evaluate(() => {
    const last = document.querySelector("main > *:last-child");
    const dockTop = document.getElementById("bottom-dock")?.getBoundingClientRect().top ?? 0;
    return last ? dockTop - last.getBoundingClientRect().bottom : -1;
  });
  expect(clear).toBeGreaterThanOrEqual(0);

  await bar.getByRole("button", { name: "Write my résumé" }).click();
  await expect(page.getByRole("alert").filter({ hasText: /read-only demo/i })).toBeVisible();
});

test("applications: stage tabs and a Move to menu replace the board", async ({ page }) => {
  await page.goto("/app/applications");
  await expect(page.getByRole("region", { name: "Applied" })).toHaveCount(0);

  await page.getByRole("tab", { name: /^Applied/ }).click();
  const move = page.getByLabel("Move to…").first();
  await expect(move).toBeVisible();
  await move.selectOption({ label: "Offer" });
  await expect(page.getByRole("alert").filter({ hasText: /read-only demo/i })).toBeVisible();
});

test("tabs: the page rises in when the tab changes, and not with reduced motion", async ({ page }) => {
  await page.goto("/app/jobs");
  await expect(page.getByRole("main").getByRole("listitem").first()).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Main" }).last();
  const animation = () =>
    page.evaluate(() => {
      const node = document.querySelector(".route-enter");
      return node ? getComputedStyle(node).animationName : null;
    });

  await nav.getByRole("link", { name: "Applications" }).click();
  await expect(page).toHaveURL(/\/app\/applications$/);
  expect(await animation()).toBe("route-enter");

  await page.emulateMedia({ reducedMotion: "reduce" });
  await nav.getByRole("link", { name: "Profile" }).click();
  await expect(page).toHaveURL(/\/app\/profile$/);
  expect(await animation()).toBe("none");
});

test("discover: the card and its action buttons fit above the dock", async ({ page }) => {
  await page.goto("/app/discover");
  const card = page.getByRole("article").first();
  await expect(card).toBeVisible();
  const buttons = page.getByRole("button", { name: /\(→\)$/ });
  await expect(buttons).toBeVisible();
  const [box, button, dock] = await Promise.all([
    card.boundingBox(),
    buttons.boundingBox(),
    page.locator("#bottom-dock").boundingBox(),
  ]);
  if (!box || !button || !dock) throw new Error("deck not laid out");
  expect(box.y + box.height).toBeLessThanOrEqual(button.y);
  expect(button.y + button.height).toBeLessThanOrEqual(dock.y + 0.5);
});
