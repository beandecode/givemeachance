import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { expect } from "@playwright/test";

/** WCAG 2.1 A/AA checks on the current page; fails with the rule ids and offending elements. */
export async function expectAccessible(page: Page) {
  // A page that is still fading in (route change) would be measured at partial opacity, which is not what people see.
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((animation) => (animation as CSSAnimation).animationName === "route-enter")
        .map((animation) => animation.finished.catch(() => undefined)),
    ),
  );
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const problems = results.violations.map(
    (violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(" | ")}`,
  );
  expect(problems).toEqual([]);
}

export async function signUp(page: Page) {
  const username = `e2e_${String(Date.now())}`;
  await page.goto("/app/");
  await expect(page).toHaveURL(/\/app\/login/);
  await page.getByRole("button", { name: "Create an account" }).click();
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Set up your job search" })).toBeVisible();
  return username;
}
