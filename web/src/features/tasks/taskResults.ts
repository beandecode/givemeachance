import { client, unwrap } from "@/api/client";

/** What a finished task says about its outcome, as one toast. */
export interface ResultNotice {
  title: string;
  description?: string;
  tone: "success" | "info";
  /** Jobs that were saved but have no score yet. */
  notScored: number;
}

function num(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function jobs(count: number): string {
  return `${String(count)} ${count === 1 ? "job" : "jobs"}`;
}

/** The result JSON of a task (only for tasks that succeeded). */
export async function fetchTaskResult(taskId: string): Promise<unknown> {
  return unwrap(client.GET("/api/v1/tasks/{task_id}/result", { params: { path: { task_id: taskId } } }));
}

/** "Found 12 new jobs", "10 scored · 2 not scored (daily AI limit reached) · 3 already saved ...". */
export function searchNotice(raw: unknown): ResultNotice {
  const result = record(raw);
  const inserted = num(result.inserted_count);
  const scored = num(result.evaluated_count);
  const byQuota = num(result.not_scored_by_quota);
  const byChoice = num(result.not_scored_by_choice);
  const failed = Array.isArray(result.failed_job_ids) ? result.failed_job_ids.length : 0;
  const noText = num(result.not_scored_no_description);
  const duplicates = num(result.duplicates_skipped);
  const skippedByLevel = num(result.skipped_by_level);
  const skippedByFilters = Object.values(record(result.skipped_by_filters)).reduce<number>(
    (sum, value) => sum + num(value),
    0,
  );
  const notScored = num(result.not_scored_count);

  const parts: string[] = [];
  if (inserted > 0) {
    if (scored > 0) parts.push(`${String(scored)} scored`);
    if (byQuota > 0) parts.push(`${String(byQuota)} not scored (daily AI limit reached)`);
    if (failed > 0) parts.push(`${String(failed)} could not be scored`);
    if (noText > 0) parts.push(`${String(noText)} not scored (full description unavailable)`);
    if (byChoice > 0) parts.push(`${String(byChoice)} not scored yet`);
  }
  if (duplicates > 0) parts.push(`${String(duplicates)} already saved`);
  if (skippedByLevel > 0) parts.push(`${String(skippedByLevel)} skipped by level`);
  if (skippedByFilters > 0) parts.push(`${String(skippedByFilters)} skipped by your filters`);
  if (inserted === 0 && parts.length === 0) parts.push("Try other keywords or a wider date range.");

  return {
    title:
      inserted === 0
        ? "No new jobs found"
        : `Found ${String(inserted)} new ${inserted === 1 ? "job" : "jobs"}`,
    description: parts.join(" · "),
    tone: notScored > 0 || result.quota_exhausted === true ? "info" : "success",
    notScored,
  };
}

/** "Scored 8 of 10 jobs", with the reason for any that were not. */
export function rescoreNotice(raw: unknown): ResultNotice {
  const result = record(raw);
  const target = num(result.target_job_count);
  const scored = num(result.evaluated_count);
  const notAttempted = num(result.not_attempted_count);
  const noText = num(result.needs_description_count);
  const failed = Array.isArray(result.failed_job_ids) ? result.failed_job_ids.length : 0;
  if (target === 0) return { title: "Nothing to score", tone: "info", notScored: 0 };

  const parts: string[] = [];
  if (notAttempted > 0) parts.push(`${String(notAttempted)} not scored (daily AI limit reached)`);
  if (failed > 0) parts.push(`${String(failed)} could not be scored`);
  if (noText > 0)
    parts.push(`${String(noText)} not scored (full description unavailable: paste it on the job page)`);
  return {
    title: `Scored ${String(scored)} of ${jobs(target)}`,
    description: parts.join(" · ") || undefined,
    tone: parts.length > 0 ? "info" : "success",
    notScored: notAttempted + failed + noText,
  };
}

export const RESULT_NOTICES: Record<string, (raw: unknown) => ResultNotice> = {
  manual_search: searchNotice,
  re_evaluate: rescoreNotice,
};
