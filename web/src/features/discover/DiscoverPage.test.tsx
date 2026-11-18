import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { journey, ok, server } from "@/test/server";
import { renderRoute } from "@/test/render";

import { DEFAULT_PREFERENCES } from "./actions";
import { useLocation } from "react-router";

import { DiscoverPage } from "./DiscoverPage";

function job(id: number, title: string, score: number) {
  return {
    id,
    title,
    company: `Company ${String(id)}`,
    location: "Toronto",
    source: "adzuna",
    url: "",
    posted_date: "2026-10-01",
    created_at: "2026-10-01T00:00:00Z",
    salary_min: null,
    salary_max: null,
    match_score: score,
    years_asked_min: id === 1 ? 3 : null,
    years_asked_max: id === 1 ? 5 : null,
    recommendation_level: "strong_yes",
    confidence: "high",
    source_profile_id: 1,
    source_profile_version: 1,
    application_status: "draft",
    application_note: "",
    archived_at: null,
    triage: null,
    triage_generate: null,
    has_resume: false,
    has_cover_letter: false,
  };
}

const JOBS = [job(1, "Platform Engineer", 91), job(2, "Data Engineer", 84), job(3, "SRE", 77)];

function detail(id: number) {
  return {
    ...(JOBS.find((entry) => entry.id === id) ?? JOBS[0]),
    description: "Build and run the platform.",
    description_is_snippet: false,
    match: {
      total_score: 91,
      match_score: 91,
      dimension_scores: { skills_match: 90, seniority_match: 80 },
      match_reasons: ["Python and Kubernetes match your last role"],
      strengths: [],
      gaps: ["No Terraform on your profile"],
      risk_flags: [],
      recommendation_level: "strong_yes",
      confidence: "high",
      missing_information: [],
      fit_reason: "",
      should_apply: true,
      model_name: "mock",
      created_at: "2026-10-01T00:00:00Z",
      source_profile_id: 1,
      source_profile_version: 1,
    },
    match_uses_latest_profile: true,
    decision: null,
    documents: { resume: null, cover_letter: null },
    application_updated_at: null,
  };
}

const task = (id: string, type: string, jobId: number) => ({
  task_id: id,
  task_type: type,
  owner_user_id: 1,
  state: "queued",
  correlation_id: "req_x",
  created_at_utc: "2026-10-01T00:00:00Z",
  started_at_utc: null,
  finished_at_utc: null,
  progress_percent: 0,
  progress_stage: "queued",
  error_code: null,
  error_message_safe: null,
  result_ref: null,
  cancel_requested: false,
  job_id: jobId,
});

function serve(preferences = DEFAULT_PREFERENCES, unscored = 0) {
  const triage: { jobId: string; body: unknown }[] = [];
  const undone: string[] = [];
  server.use(
    http.get("*/api/v1/preferences", () => ok(preferences)),
    http.get("*/api/v1/jobs", ({ request }) => {
      const url = new URL(request.url);
      if (url.searchParams.get("scored") === "false") {
        return ok({ items: [], total: unscored, limit: 1, offset: 0 });
      }
      if (url.searchParams.get("triage") === "accepted") {
        return ok({ items: [], total: 0, limit: 100, offset: 0 });
      }
      return ok({ items: JOBS, total: JOBS.length, limit: 50, offset: 0 });
    }),
    http.get("*/api/v1/jobs/:id", ({ params }) => ok(detail(Number(params.id)))),
    http.put("*/api/v1/jobs/:id/triage", async ({ params, request }) => {
      const body = (await request.json()) as { action: string };
      triage.push({ jobId: String(params.id), body });
      const tasks = body.action === "accepted" ? [task("t1", "generate_resume", Number(params.id))] : [];
      return ok({
        job_id: Number(params.id),
        action: body.action,
        generate: null,
        tasks,
        queued_for_later: false,
      });
    }),
    http.delete("*/api/v1/jobs/:id/triage", ({ params }) => {
      undone.push(String(params.id));
      return ok(detail(Number(params.id)));
    }),
    http.get("*/api/v1/tasks/:id", () => ok(task("t1", "generate_resume", 1))),
  );
  return { triage, undone };
}

function StateProbe() {
  const from = (useLocation().state as { from?: string } | null)?.from;
  return <p>{`Job page from ${from ?? "nowhere"}`}</p>;
}

function renderDeck() {
  return renderRoute(
    [
      { path: "/discover", element: <DiscoverPage /> },
      { path: "/jobs/:jobId", element: <StateProbe /> },
    ],
    "/discover",
  );
}

describe("DiscoverPage", () => {
  it("shows the best match first with its reasons, and the count above the threshold", async () => {
    serve();
    renderDeck();

    expect(
      await screen.findByRole("article", { name: "Platform Engineer at Company 1" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Match score 91 out of 100" })).toBeInTheDocument();
    expect(screen.getByText("Asks for 3 to 5 years")).toBeInTheDocument();
    expect(await screen.findByText("Python and Kubernetes match your last role")).toBeInTheDocument();
    expect(screen.getByText("3 new jobs at 70 or above")).toBeInTheDocument();
  });

  it("right arrow writes a résumé, left skips, up waitlists, and the next card comes forward", async () => {
    const { triage } = serve();
    renderDeck();
    await screen.findByRole("article", { name: "Platform Engineer at Company 1" });
    const user = userEvent.setup();

    await user.keyboard("{ArrowRight}");
    expect(await screen.findByRole("article", { name: "Data Engineer at Company 2" })).toBeInTheDocument();
    await user.keyboard("{ArrowLeft}");
    expect(await screen.findByRole("article", { name: "SRE at Company 3" })).toBeInTheDocument();
    await user.keyboard("{ArrowUp}");

    await waitFor(() => {
      expect(triage).toEqual([
        { jobId: "1", body: { action: "accepted", generate: "resume" } },
        { jobId: "2", body: { action: "skipped" } },
        { jobId: "3", body: { action: "waitlisted" } },
      ]);
    });
    expect(await screen.findByText("You have decided on every job")).toBeInTheDocument();
  });

  it("down opens the full job page without deciding", async () => {
    const { triage } = serve();
    renderDeck();
    await screen.findByRole("article", { name: "Platform Engineer at Company 1" });

    await userEvent.setup().keyboard("{ArrowDown}");

    expect(await screen.findByText("Job page from discover")).toBeInTheDocument();
    expect(triage).toEqual([]);
  });

  it("uses the user's own mapping", async () => {
    const { triage } = serve({
      ...DEFAULT_PREFERENCES,
      swipe: { left: "waitlist", right: "skip", up: "generate_resume_and_cover_letter", down: "none" },
    });
    renderDeck();
    await screen.findByRole("article", { name: "Platform Engineer at Company 1" });
    const user = userEvent.setup();

    await user.keyboard("{ArrowLeft}");
    await user.keyboard("{ArrowUp}");
    await user.keyboard("{ArrowDown}");

    await waitFor(() => {
      expect(triage).toEqual([
        { jobId: "1", body: { action: "waitlisted" } },
        { jobId: "2", body: { action: "accepted", generate: "resume_and_cover_letter" } },
      ]);
    });
  });

  it("buttons decide too, and Undo brings the card back", async () => {
    const { triage, undone } = serve();
    renderDeck();
    await screen.findByRole("article", { name: "Platform Engineer at Company 1" });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Skip (←)" }));
    expect(await screen.findByRole("article", { name: "Data Engineer at Company 2" })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Undo" }));

    expect(
      await screen.findByRole("article", { name: "Platform Engineer at Company 1" }),
    ).toBeInTheDocument();
    expect(triage).toEqual([{ jobId: "1", body: { action: "skipped" } }]);
    expect(undone).toEqual(["1"]);
  });

  it("keeps the actions reachable for assistive tech when the buttons are switched off", async () => {
    serve({ ...DEFAULT_PREFERENCES, deck: { ...DEFAULT_PREFERENCES.deck, buttons: false } });
    renderDeck();
    await screen.findByRole("article", { name: "Platform Engineer at Company 1" });

    const skip = screen.getByRole("button", { name: "Skip (←)" });
    expect(skip.parentElement).toHaveClass("sr-only");
  });

  it("explains an empty deck and offers the next step", async () => {
    server.use(
      http.get("*/api/v1/preferences", () => ok(DEFAULT_PREFERENCES)),
      http.get("*/api/v1/jobs", () => ok({ items: [], total: 0, limit: 50, offset: 0 })),
    );
    renderDeck();

    expect(await screen.findByText("You have decided on every job")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All jobs" })).toHaveAttribute("href", "/jobs");
  });

  it.each([
    ["no_jobs", "No jobs yet"],
    ["none_scored", "Your jobs are not scored yet"],
    ["below_threshold", "Nothing at 70 or above"],
  ])("tells apart why the deck is empty (%s)", async (state, title) => {
    server.use(
      http.get("*/api/v1/preferences", () => ok(DEFAULT_PREFERENCES)),
      http.get("*/api/v1/jobs", () => ok({ items: [], total: 0, limit: 50, offset: 0 })),
      http.get("*/api/v1/journey", () => ok(journey({ discover: state }))),
    );
    renderDeck();

    expect(await screen.findByText(title)).toBeInTheDocument();
  });

  it("says how many jobs are not scored yet and links to them", async () => {
    serve(DEFAULT_PREFERENCES, 4);
    renderDeck();

    expect(
      await screen.findByText(/4 jobs aren't scored yet, so they aren't in the deck/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Score them" })).toHaveAttribute("href", "/jobs?view=unscored");
  });
});
