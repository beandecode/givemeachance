import { expect, test } from "@playwright/test";

const OUT = "../docs/images";
const BASE = "http://127.0.0.1:5097";

// Not part of `npm run e2e`: run with `npm run screenshots` (needs the built app and Chromium).
test("README screenshots of the seeded demo", async ({ page, browser }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/app/jobs");
  const links = page.getByRole("main").getByRole("listitem").getByRole("link");
  await expect(links.first()).toBeVisible();
  await page.getByLabel("Sort").selectOption("score");
  await expect(links.first()).toBeVisible();
  await page.screenshot({ path: `${OUT}/jobs.png` });

  // The strongest match: explanation, then its generated résumé
  await links.first().click();
  await expect(page.getByRole("heading", { name: "Why it fits" })).toBeVisible();
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/job-match.png` });
  await expect(page.locator(".doc-preview h1").first()).toBeVisible();
  // A window tall enough for the whole document, so the sticky header never lands on top of it.
  await page.setViewportSize({ width: 1440, height: 2000 });
  await page.getByRole("tabpanel").scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.getByRole("tabpanel").screenshot({ path: `${OUT}/job-resume.png` });
  await page.setViewportSize({ width: 1440, height: 900 });

  // From 1536 px the board shows all eight stages in two rows without scrolling.
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.getByRole("link", { name: "Applications" }).first().click();
  await expect(page.getByRole("region", { name: "Rejected" })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/board.png` });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("link", { name: "Profile" }).first().click();
  await expect(page.getByRole("heading", { name: "Profile", level: 1 })).toBeVisible();
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/profile.png` });
  // The gap questions the profile builder raised, as the read-only demo shows them.
  const gaps = page.locator('[data-tour="gaps"]');
  await expect(gaps).toBeVisible();
  await gaps.screenshot({ path: `${OUT}/profile-gaps.png` });

  // The résumé step of the demo: what the real form takes, and a sample résumé in four formats.
  await page.goto("/app/onboarding?step=background");
  await expect(page.getByRole("heading", { name: "Try it with a sample résumé" })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/resume-input.png` });

  const dark = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "dark" });
  const night = await dark.newPage();
  await night.goto(`${BASE}/app/jobs`);
  await expect(night.getByRole("main").getByRole("listitem").getByRole("link").first()).toBeVisible();
  await night.screenshot({ path: `${OUT}/jobs-dark.png` });

  // The swipe deck with the card held part-way to the right: the stamp names what letting go will do.
  await night.goto(`${BASE}/app/discover`);
  const card = night.getByRole("article").first();
  await expect(card).toBeVisible();
  await expect(night.getByText("Open the full job page")).toBeVisible();
  await night.waitForTimeout(600);
  // The case study shows the deck at rest, without the half-way stamp.
  await night.screenshot({ path: `${OUT}/../../app/case_study/discover.png` });
  const box = await card.boundingBox();
  if (!box) throw new Error("deck card not laid out");
  await night.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await night.mouse.down();
  await night.mouse.move(box.x + box.width / 2 + 46, box.y + box.height / 2 + 4, { steps: 8 });
  await night.waitForTimeout(400);
  await night.screenshot({ path: `${OUT}/discover.png` });
  await night.mouse.up();
  await dark.close();

  const nightPhone = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    colorScheme: "dark",
  });
  const deckPhone = await nightPhone.newPage();
  await deckPhone.goto(`${BASE}/app/discover`);
  await expect(deckPhone.getByRole("article").first()).toBeVisible();
  await deckPhone.waitForTimeout(500);
  await deckPhone.screenshot({ path: `${OUT}/discover-phone.png` });
  await nightPhone.close();

  const phone = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  const mobile = await phone.newPage();
  await mobile.goto(`${BASE}/app/jobs`);
  const rows = mobile.getByRole("main").getByRole("listitem");
  await expect(rows.first().getByRole("link")).toBeVisible();
  await mobile.screenshot({ path: `${OUT}/jobs-phone.png` });

  // A saved job has no documents yet, so the bar offers to write the résumé.
  await rows.filter({ hasText: "Saved" }).getByRole("link").first().click();
  await expect(mobile.getByRole("region", { name: "Next step" })).toBeVisible();
  await mobile.screenshot({ path: `${OUT}/job-phone.png` });

  await mobile
    .getByRole("navigation", { name: "Main" })
    .last()
    .getByRole("link", { name: "Applications" })
    .click();
  await mobile.getByRole("tab", { name: /^Applied/ }).click();
  await expect(mobile.getByLabel("Move to…").first()).toBeVisible();
  await mobile.screenshot({ path: `${OUT}/board-phone.png` });
  await phone.close();
});
