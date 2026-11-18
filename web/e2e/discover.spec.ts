import type { Page } from "@playwright/test";
import { expect, test } from "@playwright/test";

import { expectAccessible } from "./helpers";
import { seedJobs, seedProfile, total } from "./seed";

function deckCount(page: Page, count: number) {
  return page.getByText(new RegExp(`^${String(count)} new jobs? at 0 or above$`));
}

test("Discover: arrow keys, mouse drag, buttons and undo record decisions", async ({ page }) => {
  await seedProfile(page);
  await seedJobs(page);
  const pending = await total(page, "pending");
  expect(pending).toBeGreaterThanOrEqual(3);

  await page.goto("/app/discover");
  const card = page.getByRole("article").first();
  await expect(card).toBeVisible();
  await expect(deckCount(page, pending)).toBeVisible();
  await expectAccessible(page);

  // Right arrow: accepted, and a résumé starts
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => total(page, "accepted")).toBe(1);
  await expect(deckCount(page, pending - 1)).toBeVisible();

  // Dragging the card with the mouse past the threshold to the left skips it
  const box = await page.getByRole("article").first().boundingBox();
  if (!box) throw new Error("card not laid out");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 - 60, box.y + box.height / 2, { steps: 5 });
  await page.mouse.move(box.x + box.width / 2 - 220, box.y + box.height / 2, { steps: 8 });
  await page.mouse.up();
  await expect.poll(() => total(page, "skipped")).toBe(1);

  // The on-card button waitlists; Undo brings the last decision back
  await page.getByRole("button", { name: "Waitlist (↑)" }).click();
  await expect.poll(() => total(page, "waitlisted")).toBe(1);
  await page.getByRole("button", { name: "Undo" }).first().click();
  await expect.poll(() => total(page, "waitlisted")).toBe(0);
  await expect(deckCount(page, pending - 2)).toBeVisible();

  // Down opens the full job page and decides nothing
  await page.keyboard.press("ArrowDown");
  await expect(page).toHaveURL(/\/app\/jobs\/\d+$/);
  expect(await total(page, "pending")).toBe(pending - 2);

  // ...and the back link names the deck and returns to it
  await page.getByRole("link", { name: "Back to the deck" }).click();
  await expect(page).toHaveURL(/\/app\/discover$/);
  await expect(page.getByRole("article").first()).toBeVisible();
});

test("Settings: a remapped swipe and the score threshold change how the deck behaves", async ({ page }) => {
  await seedProfile(page);
  await seedJobs(page);
  await page.goto("/app/settings");
  await expectAccessible(page);

  // Left now waitlists (swapping with up, which now skips); buttons are switched off
  await page.getByLabel(/Swipe left/).selectOption("waitlist");
  await expect(page.getByLabel(/Swipe up/)).toHaveValue("skip");
  await page.getByRole("switch", { name: /Show buttons under the card/ }).click();
  await expect
    .poll(async () => {
      const body = (await (await page.request.get("/api/v1/preferences")).json()) as {
        data: { swipe: { left: string; up: string }; deck: { buttons: boolean } };
      };
      return `${body.data.swipe.left}/${body.data.swipe.up}/${String(body.data.deck.buttons)}`;
    })
    .toBe("waitlist/skip/false");

  await page.goto("/app/discover");
  await expect(page.getByRole("article").first()).toBeVisible();
  // Kept for keyboards and screen readers, but visually hidden
  await expect(page.getByRole("button", { name: "Waitlist (←)" }).locator("..")).toHaveClass(/sr-only/);
  await page.keyboard.press("ArrowLeft");
  await expect.poll(() => total(page, "waitlisted")).toBe(1);

  // The waitlist view lists it, and "Back to Discover" returns it to the deck
  await page.goto("/app/jobs?view=waitlisted");
  await expect(page.getByRole("main").getByRole("listitem")).toHaveCount(1);
  await page.getByRole("button", { name: "Back to Discover" }).click();
  await expect(page.getByText("Your waitlist is empty")).toBeVisible();
  await expect.poll(() => total(page, "waitlisted")).toBe(0);

  // A threshold above every score empties the deck
  await page.goto("/app/settings");
  await page.getByLabel(/Minimum match score/).fill("100");
  await page.goto("/app/discover");
  await expect(page.getByText("Nothing at 100 or above")).toBeVisible();
});

test("Discover: long text in the side panel stays inside it", async ({ page }) => {
  await seedProfile(page);
  await seedJobs(page);
  // A long unbroken string is the worst case for a grid column that sizes itself to its content.
  const deck = (await (
    await page.request.get("/api/v1/jobs?triage=pending&min_score=0&sort=score&limit=1")
  ).json()) as {
    data: { items: { id: number }[] };
  };
  const first = deck.data.items[0];
  if (!first) throw new Error("no job in the deck");
  const saved = await page.request.put(`/api/v1/jobs/${String(first.id)}/description`, {
    data: {
      description: `${"Pragmatikeverylongunbrokenword".repeat(14)} then a normal sentence. `.repeat(3),
    },
  });
  expect(saved.ok()).toBe(true);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/app/discover");
  const panel = page.getByRole("complementary", { name: "About this job" });
  await expect(panel).toBeVisible();
  await expect(panel.getByText(/Pragmatikeverylong/)).toBeVisible();

  const overflow = await panel.evaluate((aside) => {
    // Real postings have long titles too: put some into the "Up next" rows.
    aside.querySelectorAll("ul li > span:first-child").forEach((title) => {
      title.textContent =
        "Senior Backend Software Engineer (Marketing and Privacy Engineering) at a company ".repeat(3);
    });
    const edge = aside.getBoundingClientRect().right;
    return Array.from(aside.querySelectorAll("*")).filter((el) => el.getBoundingClientRect().right > edge + 1)
      .length;
  });
  expect(overflow).toBe(0);
  expect(await panel.evaluate((aside) => aside.scrollWidth - aside.clientWidth)).toBeLessThanOrEqual(0);
});
