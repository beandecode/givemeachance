import { expect, test } from "@playwright/test";

import { expectAccessible } from "./helpers";
import { APP_PAGES, horizontalOverflow, openPage, widestContentBlock } from "./pages";

// Runs on the seeded demo server at phone, tablet, desktop and wide-desktop sizes (see playwright.config.ts).
for (const name of APP_PAGES) {
  test(`${name}: accessible, nothing sticks out sideways, content does not stretch`, async ({ page }) => {
    await openPage(page, name);

    await expectAccessible(page);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    expect(await widestContentBlock(page)).toBeLessThanOrEqual(1600);
  });
}

test("job: the next step is a bar below 1024 px and a side card from there", async ({ page }) => {
  await page.goto("/app/jobs");
  await page
    .getByRole("main")
    .getByRole("listitem")
    .filter({ hasText: "Saved" })
    .getByRole("link")
    .first()
    .click();
  const action = page.getByRole("button", { name: "Write my résumé" });
  await expect(action).toBeVisible();
  const bar = page.getByRole("region", { name: "Next step" });
  const narrow = (page.viewportSize()?.width ?? 0) < 1024;
  await expect(bar).toHaveCount(narrow ? 1 : 0);
  await expectAccessible(page);
});
