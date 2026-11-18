import type { APIRequestContext, Page } from "@playwright/test";
import { expect } from "@playwright/test";

export async function waitForTask(request: APIRequestContext, taskId: string) {
  await expect
    .poll(
      async () => {
        const body = (await (await request.get(`/api/v1/tasks/${taskId}`)).json()) as {
          data: { state: string };
        };
        return body.data.state;
      },
      { timeout: 60_000 },
    )
    .toBe("succeeded");
}

/** A fresh account with an approved profile, set up through the API (the UI path has its own spec). */
export async function seedProfile(page: Page) {
  const request = page.request;
  const username = `deck_${String(Date.now())}`;
  expect(
    (await request.post("/api/v1/account", { data: { username, password: "e2e-password-123" } })).ok(),
  ).toBe(true);
  const synthesis = (await (
    await request.post("/api/v1/profile/synthesize", {
      data: {
        resume_text: "Alex Rivera, Backend Engineer. 6 years with Python, Flask, SQL, Docker and AWS.",
        links: [],
        user_details: {
          candidate_name: "Alex Rivera",
          target_roles: ["Backend Engineer"],
          key_skills: "Python, SQL, Flask, AWS",
        },
      },
    })
  ).json()) as { data: { task_id: string } };
  await waitForTask(request, synthesis.data.task_id);
  const result = (await (await request.get(`/api/v1/tasks/${synthesis.data.task_id}/result`)).json()) as {
    data: { profile_id: number };
  };
  expect(
    (
      await request.post(`/api/v1/profile/${String(result.data.profile_id)}/review`, {
        data: { review_status: "approved", review_note: "" },
      })
    ).ok(),
  ).toBe(true);
}

/** Searches the job board and makes the Discover deck show every job (mock scores can sit below the default 70). */
export async function seedJobs(page: Page) {
  const request = page.request;
  const search = (await (await request.post("/api/v1/searches", { data: {} })).json()) as {
    data: { task_id: string };
  };
  await waitForTask(request, search.data.task_id);
  // Mock scores can sit below the default threshold of 70; the deck should show every job here.
  expect(
    (
      await request.put("/api/v1/preferences", {
        data: {
          swipe: { left: "skip", right: "generate_resume", up: "waitlist", down: "details" },
          deck: { min_score: 0, mouse_drag: true, buttons: true },
          ui: { glass: "auto" },
        },
      })
    ).ok(),
  ).toBe(true);
}

/** How many of the user's jobs have this swipe state ("pending", "skipped", "waitlisted", "accepted"). */
export async function total(page: Page, triage: string) {
  const body = (await (await page.request.get(`/api/v1/jobs?triage=${triage}&limit=100`)).json()) as {
    data: { total: number };
  };
  return body.data.total;
}
