import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

/** Wrap data in the API's success envelope. */
export function ok(data: unknown, status = 200) {
  return HttpResponse.json({ status: "ok", correlation_id: "req_test", data }, { status });
}

export function apiError(status: number, error_code: number, message: string) {
  return HttpResponse.json(
    { status: "error", error_code, message, correlation_id: "req_test_error" },
    { status },
  );
}

export const readiness = {
  allowed: true,
  profile_id: 1,
  profile_version: 1,
  review_status: "approved",
  completeness_score: 80,
  high_priority_missing_count: 0,
  blocking_reasons: [],
  suggested_actions: [],
  checked_at: "2026-10-20T00:00:00Z",
};

const STEP_KEYS = ["profile", "search_prefs", "find_jobs", "pick", "write", "apply"];

/** A finished journey by default (the guide bar stays hidden); `discover` sets why the deck is empty. */
export function journey(overrides: Record<string, unknown> = {}) {
  return {
    completed: true,
    skipped: false,
    current: null,
    steps: STEP_KEYS.map((key) => ({
      key,
      status: "done",
      reason_code: null,
      cta_label: "",
      cta_route: "",
    })),
    counts: { jobs: 6, scored: 6, deck: 0, pending: 0, accepted: 1, documents: 1, applied: 1 },
    discover: "all_decided",
    ...overrides,
  };
}

/** Endpoints every signed-in screen touches; tests override what they care about. */
export const baseHandlers = [
  http.get("*/api/v1/session", () => ok({ user: { id: 1, username: "alex", is_admin: false } })),
  http.get("*/api/v1/config", () =>
    ok({
      registration_open: false,
      demo_mode: false,
      demo_live: false,
      guest: false,
      llm_provider: "mock",
      job_source: "mock",
      search_results_per_run: 10,
    }),
  ),
  http.get("*/api/v1/overview", () =>
    ok({ counts: { jobs: 0, evaluated: 0, applications: 0 }, readiness, usage: [] }),
  ),
  http.get("*/api/v1/journey", () => ok(journey())),
  http.get("*/api/v1/search-suggestions", () => ok([])),
  http.get("*/api/v1/tasks", () => ok({ items: [], total: 0, limit: 50, offset: 0 })),
  http.get("*/api/v1/search-preferences", () =>
    ok({
      source: "user",
      config: {
        target_levels: [],
        work_modes: [],
        exclude_title_words: [],
        knockouts: [],
        adzuna: {
          country: "ca",
          keywords: ["backend engineer"],
          location: "Toronto",
          results_per_page: 10,
          max_pages: 1,
          days_old: 14,
          sort_by: "date",
          salary_min: null,
          salary_max: null,
          distance: null,
          company: null,
          category: null,
          full_time: null,
          part_time: null,
          permanent: null,
          contract: null,
          what_and: null,
          what_or: null,
          what_phrase: null,
          what_exclude: null,
        },
      },
    }),
  ),
];

export const server = setupServer(...baseHandlers);
