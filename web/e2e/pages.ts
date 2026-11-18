import type { Page } from "@playwright/test";
import { expect } from "@playwright/test";

/** The signed-in screens, reached on the seeded demo server where every one of them has content. */
export const APP_PAGES = ["discover", "jobs", "job", "applications", "profile", "settings"] as const;
export type AppPage = (typeof APP_PAGES)[number];

export async function openPage(page: Page, name: AppPage) {
  if (name === "job") {
    await page.goto("/app/jobs");
    const first = page.getByRole("main").getByRole("listitem").getByRole("link").first();
    await expect(first).toBeVisible();
    await first.click();
    await expect(page.getByRole("heading", { name: "Why it fits" })).toBeVisible();
    return;
  }
  await page.goto(`/app/${name}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  if (name === "discover") await expect(page.getByRole("article").first()).toBeVisible();
  if (name === "jobs") await expect(page.getByRole("main").getByRole("listitem").first()).toBeVisible();
  if (name === "applications") {
    // A board of regions from 1024 px, stage tabs below that.
    const board = page.getByRole("region", { name: "Applied" });
    await expect(board.or(page.getByRole("tab", { name: /^Applied/ }))).toBeVisible();
  }
}

/** Width in pixels of the widest block directly inside <main>. */
export async function widestContentBlock(page: Page): Promise<number> {
  return page.evaluate(() =>
    Math.max(
      0,
      ...Array.from(document.querySelectorAll("main > *")).map((el) => el.getBoundingClientRect().width),
    ),
  );
}

/** How far the document scrolls sideways (0 means nothing sticks out). */
export async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
}
