import { screen } from "@testing-library/react";
import { http } from "msw";
import { useEffect } from "react";
import { describe, expect, it } from "vitest";

import type { Task } from "@/api/client";
import { renderRoute } from "@/test/render";
import { apiError, ok, server } from "@/test/server";

import { useTasks } from "./TaskProvider";
import { rescoreNotice, searchNotice } from "./taskResults";

describe("searchNotice", () => {
  it("counts the jobs your filters dropped", () => {
    const notice = searchNotice({
      inserted_count: 2,
      evaluated_count: 2,
      skipped_by_filters: { salary: 1, title_word: 2, work_mode: 0, knockout: 1 },
    });
    expect(notice.description).toBe("2 scored · 4 skipped by your filters");
  });

  it("reports a full search", () => {
    const notice = searchNotice({
      inserted_count: 12,
      evaluated_count: 10,
      failed_job_ids: [],
      not_scored_by_quota: 0,
      not_scored_by_choice: 0,
      not_scored_count: 0,
      duplicates_skipped: 3,
      skipped_by_level: 4,
    });
    expect(notice).toMatchObject({ title: "Found 12 new jobs", tone: "success", notScored: 0 });
    expect(notice.description).toBe("10 scored · 3 already saved · 4 skipped by level");
  });

  it("says when the daily AI limit stopped scoring", () => {
    const notice = searchNotice({
      inserted_count: 5,
      evaluated_count: 3,
      not_scored_by_quota: 2,
      not_scored_count: 2,
      quota_exhausted: true,
    });
    expect(notice.tone).toBe("info");
    expect(notice.description).toBe("3 scored · 2 not scored (daily AI limit reached)");
    expect(notice.notScored).toBe(2);
  });

  it("says which jobs wait for their full description", () => {
    const search = searchNotice({
      inserted_count: 5,
      evaluated_count: 4,
      not_scored_no_description: 1,
      not_scored_count: 1,
    });
    expect(search.description).toBe("4 scored · 1 not scored (full description unavailable)");
    expect(search.notScored).toBe(1);
    const rescore = rescoreNotice({ target_job_count: 1, evaluated_count: 0, needs_description_count: 1 });
    expect(rescore).toMatchObject({ title: "Scored 0 of 1 job", tone: "info", notScored: 1 });
    expect(rescore.description).toMatch(/full description unavailable/);
  });

  it("reports a fetch-only search", () => {
    const notice = searchNotice({ inserted_count: 4, not_scored_by_choice: 4, not_scored_count: 4 });
    expect(notice.title).toBe("Found 4 new jobs");
    expect(notice.description).toBe("4 not scored yet");
    expect(notice.tone).toBe("info");
  });

  it("explains a search that found nothing new and survives a missing result", () => {
    expect(searchNotice({ inserted_count: 0 })).toMatchObject({
      title: "No new jobs found",
      description: "Try other keywords or a wider date range.",
    });
    expect(searchNotice(null).title).toBe("No new jobs found");
  });
});

describe("rescoreNotice", () => {
  it("reports scored jobs, quota stops and an empty run", () => {
    expect(rescoreNotice({ target_job_count: 3, evaluated_count: 3 })).toMatchObject({
      title: "Scored 3 of 3 jobs",
      tone: "success",
    });
    expect(
      rescoreNotice({ target_job_count: 5, evaluated_count: 2, not_attempted_count: 3 }).description,
    ).toBe("3 not scored (daily AI limit reached)");
    expect(rescoreNotice({ target_job_count: 0 }).title).toBe("Nothing to score");
  });
});

const task = (type: string): Task => ({
  task_id: "t_1",
  task_type: type,
  owner_user_id: 1,
  state: "succeeded",
  correlation_id: "req_x",
  created_at_utc: "2026-10-01T00:00:00Z",
  started_at_utc: null,
  finished_at_utc: "2026-10-01T00:01:00Z",
  progress_percent: 100,
  progress_stage: "persisted",
  error_code: null,
  error_message_safe: null,
  result_ref: null,
  cancel_requested: false,
  job_id: null,
});

function Follow({ type }: { type: string }) {
  const { track } = useTasks();
  useEffect(() => track(task(type)), [track, type]);
  return null;
}

describe("task toasts", () => {
  it("say what a finished search did", async () => {
    server.use(
      http.get("*/api/v1/tasks/t_1", () => ok(task("manual_search"))),
      http.get("*/api/v1/tasks/t_1/result", () =>
        ok({ inserted_count: 6, evaluated_count: 6, failed_job_ids: [], duplicates_skipped: 1 }),
      ),
    );
    renderRoute([{ path: "/", element: <Follow type="manual_search" /> }], "/");

    expect(await screen.findByText("Found 6 new jobs")).toBeInTheDocument();
    expect(screen.getByText("6 scored · 1 already saved")).toBeInTheDocument();
  });

  it("fall back to the plain title when the result cannot be read", async () => {
    server.use(
      http.get("*/api/v1/tasks/t_1", () => ok(task("manual_search"))),
      http.get("*/api/v1/tasks/t_1/result", () => apiError(409, 3004, "not ready")),
    );
    renderRoute([{ path: "/", element: <Follow type="manual_search" /> }], "/");

    expect(await screen.findByText("Search finished")).toBeInTheDocument();
  });
});
