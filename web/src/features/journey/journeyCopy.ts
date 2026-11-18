export type { JobJourney, Journey } from "@/api/client";

export const STEP_LABELS: Record<string, string> = {
  profile: "Your profile",
  search_prefs: "Search settings",
  find_jobs: "Find jobs",
  pick: "Pick jobs",
  write: "Write a résumé",
  apply: "Apply",
};

export const JOB_STEP_LABELS: Record<string, string> = {
  score: "Score",
  write: "Write",
  review: "Check",
  applied: "Apply",
  follow_up: "Follow up",
};

/** What each reason code means for the user; the server sends codes, never sentences. */
export const REASON_COPY: Record<string, string> = {
  profile_missing: "Add your résumé and we build your profile.",
  profile_incomplete: "Your profile is missing details that matching needs.",
  profile_not_approved: "Check your profile and approve it. Only approved profiles are used.",
  search_not_configured: "Choose what to search for.",
  no_jobs: "Run your first search.",
  none_scored: "Score your jobs so the good ones can appear in Discover.",
  nothing_accepted: "Swipe right on a job you like.",
  no_documents: "Write your first résumé.",
  nothing_applied: "Mark a job as applied once you have sent it.",
  not_scored: "Score this job against your profile first.",
  match_stale: "Your profile changed since this job was scored.",
  needs_current_match: "Score this job first.",
  document_warnings: "The checks found things to look at before you send it.",
  not_applied: "Mark the job as applied once you have sent it.",
  no_follow_up: "Pick a day to follow up.",
};
