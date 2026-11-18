import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { renderRoute } from "@/test/render";
import { apiError, ok, readiness, server } from "@/test/server";

import { fetchChoices, scoringsFor, SearchSheet } from "./SearchSheet";

beforeAll(() => {
  // jsdom has no native modal dialog
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close() {
    this.removeAttribute("open");
  };
});

const task = {
  task_id: "tsk_1",
  task_type: "manual_search",
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

const usage = (provider: string, remaining: number) => ({
  provider,
  usage_date: "2026-10-25",
  limit: 40,
  used: 40 - remaining,
  remaining,
  percent_used: ((40 - remaining) / 40) * 100,
  subject: "u1",
});

function serve({ llm = "gemini", demo = false, aiLeft = 30, boardLeft = 8 } = {}) {
  const calls: { path: string; body: unknown }[] = [];
  server.use(
    http.get("*/api/v1/config", () =>
      ok({
        registration_open: false,
        demo_mode: demo,
        demo_live: false,
        guest: false,
        llm_provider: llm,
        job_source: "adzuna_api",
        search_results_per_run: 10,
      }),
    ),
    http.get("*/api/v1/overview", () =>
      ok({
        counts: { jobs: 0, evaluated: 0, applications: 0 },
        readiness,
        usage: [usage("gemini", aiLeft), usage("adzuna", boardLeft)],
      }),
    ),
    http.put("*/api/v1/search-preferences", async ({ request }) => {
      const body = await request.json();
      calls.push({ path: "preferences", body });
      return ok({ source: "user", config: body });
    }),
    http.post("*/api/v1/searches", async ({ request }) => {
      calls.push({ path: "searches", body: await request.json() });
      return ok(task, 202);
    }),
    http.get("*/api/v1/tasks/tsk_1", () => ok(task)),
  );
  return calls;
}

function open() {
  const onClose = vi.fn();
  renderRoute([{ path: "/", element: <SearchSheet open onClose={onClose} /> }], "/");
  return onClose;
}

describe("helpers", () => {
  it("offers steps of five up to the server cap", () => {
    expect(fetchChoices(20)).toEqual([5, 10, 15, 20]);
    expect(fetchChoices(5)).toEqual([5]);
    expect(fetchChoices(12)).toEqual([5, 10, 12]);
  });

  it("counts the scorings a search may use", () => {
    expect(scoringsFor("all", 10, 3)).toBe(10);
    expect(scoringsFor("first", 10, 3)).toBe(3);
    expect(scoringsFor("first", 2, 8)).toBe(2);
    expect(scoringsFor("none", 10, 3)).toBe(0);
  });
});

describe("SearchSheet", () => {
  it("shows the saved search, the options and what the search will use", async () => {
    serve();
    open();

    expect(await screen.findByLabelText("Keywords")).toHaveValue("backend engineer");
    expect(screen.getByLabelText("How many new jobs to add")).toHaveValue("10");
    expect(screen.getByRole("radio", { name: "Score all new jobs" })).toBeChecked();
    expect(await screen.findByRole("status", { name: "" })).toBeDefined();
    expect(
      await screen.findByText(
        "Uses 1 job-board request (8 left today) and up to 10 AI scorings (30 left today; retries can use a few more).",
      ),
    ).toBeInTheDocument();
  });

  it("saves the preferences, then searches with the chosen options", async () => {
    const calls = serve();
    const onClose = open();
    const user = userEvent.setup();

    await user.selectOptions(await screen.findByLabelText("How many new jobs to add"), "5");
    await user.click(screen.getByRole("radio", { name: "Only add them, I will score later" }));
    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(calls.map((call) => call.path)).toEqual(["preferences", "searches"]);
    expect(calls[0]?.body).toMatchObject({ adzuna: { keywords: ["backend engineer"] }, target_levels: [] });
    expect(calls[1]?.body).toEqual({ force_when_high_missing: false, fetch_limit: 5, score_limit: 0 });
  });

  it("can score only the first few", async () => {
    const calls = serve();
    open();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("radio", { name: /Score only the first few/ }));
    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1]?.body).toEqual({ force_when_high_missing: false, fetch_limit: 10, score_limit: 5 });
  });

  it("sends no limits to score everything, as a plain click does", async () => {
    const calls = serve();
    open();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Search" }));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1]?.body).toEqual({ force_when_high_missing: false, fetch_limit: 10 });
  });

  it("warns when fewer scorings are left than the search may use", async () => {
    serve({ aiLeft: 3 });
    open();
    expect(
      await screen.findByText(/Only 3 can be scored today\. The rest are saved as not scored/),
    ).toBeInTheDocument();
  });

  it("uses sample-data wording when no real provider is used", async () => {
    serve({ llm: "mock" });
    open();
    expect(await screen.findByText("Sample data: no job-board or AI quota is used.")).toBeInTheDocument();
  });

  it("is turned off in the read-only demo", async () => {
    serve({ demo: true });
    open();
    expect(await screen.findByText(/read-only demo, so searching is turned off/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Search" })).toBeDisabled();
  });

  it("keeps the sheet open and shows the reason when the search is refused", async () => {
    serve();
    server.use(http.post("*/api/v1/searches", () => apiError(409, 3004, "a job search is already running")));
    const onClose = open();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Search" }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("A job search is already running")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
