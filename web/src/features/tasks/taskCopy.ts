import type { Task } from "@/api/client";

export const TERMINAL_STATES = new Set<Task["state"]>(["succeeded", "failed", "cancelled", "expired"]);

export function isTerminal(task: Task): boolean {
  return TERMINAL_STATES.has(task.state);
}

const TITLES: Record<string, string> = {
  generate_resume: "Tailoring your résumé",
  generate_cover_letter: "Writing your cover letter",
  manual_search: "Searching the job board",
  manual_jd_match: "Analyzing the job description",
  re_evaluate: "Re-scoring your jobs",
  synthesize_profile: "Building your profile",
  supplement_profile: "Updating your profile",
};

const DONE: Record<string, string> = {
  generate_resume: "Résumé ready",
  generate_cover_letter: "Cover letter ready",
  manual_search: "Search finished",
  manual_jd_match: "Job analyzed",
  re_evaluate: "Jobs scored",
  synthesize_profile: "Profile draft ready for review",
  supplement_profile: "Profile updated. Review the new version",
};

const STAGES: Record<string, string> = {
  queued: "Waiting to start",
  validating: "Checking the details",
  ingesting: "Fetching jobs",
  evaluating: "Scoring the match",
  generating: "Writing",
  synthesizing: "Reading your résumé",
  supplementing: "Adding your answers",
  persisted: "Saving",
};

export function taskTitle(task: Task): string {
  return TITLES[task.task_type] ?? "Working";
}

export function taskDoneTitle(task: Task): string {
  return DONE[task.task_type] ?? "Done";
}

export function taskStageLabel(task: Task): string {
  if (task.state === "queued") return STAGES.queued ?? "";
  if (task.cancel_requested && !isTerminal(task)) return "Stopping…";
  return STAGES[task.progress_stage] ?? "Working";
}

export function taskFailureMessage(task: Task): string {
  if (task.state === "cancelled") return "Stopped.";
  if (task.state === "expired") return "This task was interrupted. Please start it again.";
  return task.error_message_safe ?? "It didn't finish. Please try again.";
}
