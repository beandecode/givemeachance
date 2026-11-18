import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { ok, server } from "@/test/server";
import { renderRoute } from "@/test/render";

import { JobsPage } from "./JobsPage";

const job = {
  id: 7,
  title: "Backend Engineer",
  company: "NorthStack",
  location: "Toronto",
  source: "adzuna",
  url: "",
  posted_date: "2026-10-01",
  created_at: "2026-10-01T00:00:00Z",
  salary_min: 100000,
  salary_max: 120000,
  match_score: 88,
  years_asked_min: 5,
  years_asked_max: null,
  recommendation_level: "strong_yes",
  confidence: "high",
  source_profile_id: 1,
  source_profile_version: 1,
  application_status: "draft",
  application_note: "",
  archived_at: null,
};

describe("JobsPage", () => {
  it("lists jobs with their score and status", async () => {
    server.use(http.get("*/api/v1/jobs", () => ok({ items: [job], total: 1, limit: 20, offset: 0 })));
    renderRoute([{ path: "/jobs", element: <JobsPage /> }], "/jobs");

    expect(await screen.findByRole("link", { name: "Backend Engineer" })).toHaveAttribute("href", "/jobs/7");
    const card = within(screen.getByRole("listitem"));
    expect(card.getByRole("img", { name: "Match score 88 out of 100" })).toBeInTheDocument();
    expect(card.getByText("Strong match")).toBeInTheDocument();
    expect(card.getByText("Asks for 5+ years")).toBeInTheDocument();
    expect(card.getByText("Saved")).toBeInTheDocument();
    expect(screen.getByText("1 job")).toBeInTheDocument();
  });

  it("sends filters to the API and offers to clear them when nothing matches", async () => {
    const queries: string[] = [];
    server.use(
      http.get("*/api/v1/jobs", ({ request }) => {
        queries.push(new URL(request.url).search);
        return ok({ items: [], total: 0, limit: 20, offset: 0 });
      }),
    );
    const { router } = renderRoute(
      [{ path: "/jobs", element: <JobsPage /> }],
      "/jobs?min_score=75&sort=score",
    );

    expect(await screen.findByText("No jobs match these filters")).toBeInTheDocument();
    expect(queries[0]).toContain("min_score=75");
    expect(queries[0]).toContain("sort=score");

    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(router.state.location.search).toBe(""));
    expect(await screen.findByText("No jobs yet")).toBeInTheDocument();
  });

  it("shows the waitlist and brings a job back to Discover", async () => {
    const queries: string[] = [];
    const undone: string[] = [];
    server.use(
      http.get("*/api/v1/jobs", ({ request }) => {
        queries.push(new URL(request.url).search);
        return ok({ items: [{ ...job, triage: "waitlisted" }], total: 1, limit: 20, offset: 0 });
      }),
      http.delete("*/api/v1/jobs/:id/triage", ({ params }) => {
        undone.push(String(params.id));
        return ok({ ...job, triage: null });
      }),
    );
    renderRoute([{ path: "/jobs", element: <JobsPage /> }], "/jobs?view=waitlisted");

    expect(await screen.findByRole("link", { name: "Backend Engineer" })).toBeInTheDocument();
    expect(queries[0]).toContain("triage=waitlisted");
    expect(screen.getByText("Waitlisted")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Waitlist" })).toBeChecked();

    await userEvent.setup().click(screen.getByRole("button", { name: "Back to Discover" }));
    await waitFor(() => expect(undone).toEqual(["7"]));
  });

  it("explains an empty waitlist", async () => {
    server.use(http.get("*/api/v1/jobs", () => ok({ items: [], total: 0, limit: 20, offset: 0 })));
    renderRoute([{ path: "/jobs", element: <JobsPage /> }], "/jobs?view=waitlisted");
    expect(await screen.findByText("Your waitlist is empty")).toBeInTheDocument();
  });

  describe("jobs without a score", () => {
    const unscoredJob = {
      ...job,
      id: 9,
      title: "Platform Engineer",
      match_score: null,
      recommendation_level: null,
    };
    const queued = {
      task_id: "tsk_1",
      task_type: "re_evaluate",
      owner_user_id: 1,
      state: "queued",
      progress_percent: 0,
      progress_stage: "queued",
      correlation_id: "req_1",
      error_code: null,
      error_message_safe: null,
      result_ref: null,
      job_id: null,
      cancel_requested: false,
      created_at_utc: "2026-10-25T00:00:00Z",
      started_at_utc: null,
      finished_at_utc: null,
    };

    function serve(count: number, scoringsLeft?: number) {
      const rerun: unknown[] = [];
      const queries: string[] = [];
      server.use(
        http.get("*/api/v1/jobs", ({ request }) => {
          const url = new URL(request.url);
          queries.push(url.search);
          const unscoredOnly = url.searchParams.get("scored") === "false";
          return ok({
            items: unscoredOnly || count > 0 ? [unscoredJob] : [job],
            total: unscoredOnly ? count : 1,
            limit: 20,
            offset: 0,
          });
        }),
        http.post("*/api/v1/evaluations/rerun", async ({ request }) => {
          rerun.push(await request.json());
          return ok(queued, 202);
        }),
        http.get("*/api/v1/tasks/tsk_1", () => ok(queued)),
        ...(scoringsLeft === undefined
          ? []
          : [
              http.get("*/api/v1/config", () =>
                ok({
                  registration_open: false,
                  demo_mode: false,
                  demo_live: false,
                  guest: false,
                  llm_provider: "gemini",
                  job_source: "adzuna_api",
                  search_results_per_run: 10,
                }),
              ),
              http.get("*/api/v1/overview", () =>
                ok({
                  counts: { jobs: 0, evaluated: 0, applications: 0 },
                  readiness: { allowed: true },
                  usage: [
                    {
                      provider: "gemini",
                      usage_date: "2026-10-25",
                      limit: 40,
                      used: 40 - scoringsLeft,
                      remaining: scoringsLeft,
                      percent_used: 50,
                      subject: "u1",
                    },
                  ],
                }),
              ),
            ]),
      );
      return { rerun, queries };
    }

    it("lists them in the Not scored view with a Score button per job", async () => {
      const { rerun, queries } = serve(3);
      renderRoute([{ path: "/jobs", element: <JobsPage /> }], "/jobs?view=unscored");

      expect(await screen.findByRole("link", { name: "Platform Engineer" })).toBeInTheDocument();
      expect(queries.some((query) => query.includes("scored=false") && query.includes("limit=20"))).toBe(
        true,
      );
      expect(screen.getByRole("radio", { name: "Not scored" })).toBeChecked();

      await userEvent.setup().click(screen.getByRole("button", { name: "Score Platform Engineer" }));
      await waitFor(() => expect(rerun).toEqual([{ scope: "all", job_ids: [9] }]));
    });

    it("offers to score everything that is unscored", async () => {
      const { rerun } = serve(4);
      renderRoute([{ path: "/jobs", element: <JobsPage /> }], "/jobs");

      expect(await screen.findByText(/4 jobs aren't scored yet/)).toBeInTheDocument();
      await userEvent.setup().click(screen.getByRole("button", { name: "Score all 4" }));
      await waitFor(() => expect(rerun).toEqual([{ scope: "unscored", limit: 4 }]));
    });

    it("scores only as many as today's AI limit allows", async () => {
      const { rerun } = serve(10, 3);
      renderRoute([{ path: "/jobs", element: <JobsPage /> }], "/jobs");

      expect(
        await screen.findByText(/Scoring uses up to 3 of the 3 AI scorings left today/),
      ).toBeInTheDocument();
      await userEvent.setup().click(screen.getByRole("button", { name: "Score 3 now" }));
      await waitFor(() => expect(rerun).toEqual([{ scope: "unscored", limit: 3 }]));
    });

    it("disables scoring when none are left today", async () => {
      serve(5, 0);
      renderRoute([{ path: "/jobs", element: <JobsPage /> }], "/jobs");
      expect(await screen.findByRole("button", { name: "No scorings left today" })).toBeDisabled();
    });

    it("says nothing when every job is scored", async () => {
      serve(0);
      renderRoute([{ path: "/jobs", element: <JobsPage /> }], "/jobs");
      expect(await screen.findByRole("link", { name: "Backend Engineer" })).toBeInTheDocument();
      expect(screen.queryByText(/aren't scored yet/)).not.toBeInTheDocument();
    });
  });
});
