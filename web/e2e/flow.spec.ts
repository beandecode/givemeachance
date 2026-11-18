import { expect, test } from "@playwright/test";

import { expectAccessible, signUp } from "./helpers";

test("job-search loop: onboarding → search → tailored documents → export → board", async ({ page }) => {
  await page.goto("/app/login");
  await expectAccessible(page);
  await signUp(page);
  await expectAccessible(page);

  // 1. Résumé → profile draft
  await page
    .getByLabel("Paste your résumé")
    .fill(
      "Alex Rivera, Backend Engineer in Toronto. 6 years with Python, Flask, SQL, Docker and AWS. " +
        "Acme Corp 2020–present: led the move to Kubernetes and cut API latency by 40%.",
    );
  await page.getByLabel("Full name").fill("Alex Rivera");
  await page.getByLabel("Roles you want").fill("Backend Engineer");
  await page.getByLabel("Where you want to work").fill("Toronto");
  await page.getByRole("button", { name: "Build my profile" }).click();
  await expect(page.getByText("Building your profile…")).toBeVisible();

  // 2. Review and approve
  const approve = page.getByRole("button", { name: "Looks right, approve" });
  await expect(approve).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Alex Rivera" })).toBeVisible();
  await expectAccessible(page);
  await approve.click();

  // 3. Search preferences are prefilled from the profile
  await expect(page.getByRole("heading", { name: "What should we search for?" })).toBeVisible();
  await expect(page.getByLabel("Keywords")).toHaveValue(/Backend Engineer/);
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page.getByRole("heading", { name: "Find your first jobs" })).toBeVisible();
  await expect(page.getByText("Step 4 of 6: Find jobs")).toBeVisible();

  // 4. Search; the guide moves on to picking jobs, then open the best match
  await page.getByRole("button", { name: "Search job board" }).click();
  await expect(page.getByText(/^Found \d+ new jobs?$/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("heading", { name: "Pick the jobs you like" })).toBeVisible();
  await expectAccessible(page);
  await page.goto("/app/jobs");
  await page.getByLabel("Sort").selectOption("score");
  const jobLinks = page.getByRole("main").getByRole("listitem").getByRole("link");
  await expect(jobLinks.first()).toBeVisible();
  await expectAccessible(page);
  await jobLinks.first().click();
  await expect(page.getByRole("heading", { name: "Why it fits" })).toBeVisible();
  await expectAccessible(page);

  // 5. Generate a résumé; reloading mid-task picks the progress back up
  await page.getByRole("button", { name: "Write my résumé" }).click();
  await expect(page.getByText("Writing your résumé…")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Writing your résumé…")).toBeVisible();
  const version = page.getByLabel("résumé version");
  await expect(version).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Résumé ready")).toBeVisible();
  await expect(page.locator(".doc-preview h1")).toBeVisible();

  // 6. Edit → saved as a new version; the original stays selectable
  await page.getByRole("button", { name: "Edit" }).click();
  const editor = page.getByLabel("Edit résumé (Markdown)");
  await editor.fill(`# Alex Rivera\n\n${await editor.inputValue()}`);
  await page.getByRole("button", { name: "Save as new version" }).click();
  await expect(page.getByText("Saved as version 2")).toBeVisible();
  await expect(version.locator("option")).toHaveCount(2);
  await expect(page.getByText("Edited by you")).toBeVisible();

  // 7. Export PDF and Word
  for (const [label, extension] of [
    ["PDF", "pdf"],
    ["Word", "docx"],
  ] as const) {
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("link", { name: label, exact: true }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(new RegExp(`-resume-v2\\.${extension}$`));
  }

  // 8. Cover letter in the other tab
  await page.getByRole("tab", { name: /Cover letter/ }).click();
  await page.getByRole("button", { name: "Write my cover letter" }).click();
  await expect(page.getByLabel("cover letter version")).toBeVisible({ timeout: 30_000 });

  // 9. Board: the job is "Ready to apply"; drag it to "Applied", then use the card menu (keyboard path)
  await page.getByRole("link", { name: "Applications" }).first().click();
  const column = (name: string) => page.getByRole("region", { name });
  const cards = (name: string) => column(name).getByRole("button", { name: /^Drag / });
  await expect(cards("Ready to apply")).toHaveCount(1);
  await expectAccessible(page);
  const from = await cards("Ready to apply").first().boundingBox();
  const to = await column("Applied").boundingBox();
  if (!from || !to) throw new Error("board not laid out");
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(from.x + 40, from.y + 10, { steps: 5 });
  await page.mouse.move(to.x + to.width / 2, to.y + 60, { steps: 10 });
  await page.mouse.up();
  await expect(cards("Applied")).toHaveCount(1);
  const saved = page.waitForResponse(
    (r) => r.url().endsWith("/application") && r.request().method() === "PATCH",
  );
  await column("Applied").getByRole("combobox").selectOption("interview");
  await expect(cards("Interviewing")).toHaveCount(1);
  await saved; // the card moves at once; reload only after the change is stored
  await page.reload();
  await expect(cards("Interviewing")).toHaveCount(1);

  // 10. Profile and settings pages render and pass the accessibility checks
  await page.getByRole("link", { name: "Profile" }).first().click();
  await expect(page.getByRole("heading", { name: "Profile", level: 1 })).toBeVisible();
  await expectAccessible(page);
  await page.getByRole("link", { name: "Settings" }).first().click();
  await expect(page.getByRole("heading", { name: "Discover deck" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open the Jobs page" })).toBeVisible();
  await expectAccessible(page);
});
