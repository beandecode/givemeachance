import type { Preferences } from "@/api/client";

import type { Direction } from "./swipe";

export type SwipeAction = Preferences["swipe"]["left"];

export const DEFAULT_PREFERENCES: Preferences = {
  swipe: { left: "skip", right: "generate_resume", up: "waitlist", down: "details" },
  deck: { min_score: 70, mouse_drag: true, buttons: true },
  ui: { glass: "auto" },
};

export const ACTION_LABELS: Record<SwipeAction, string> = {
  skip: "Skip",
  generate_resume: "Write résumé",
  generate_resume_and_cover_letter: "Résumé + letter",
  waitlist: "Waitlist",
  details: "Details",
  none: "Nothing",
};

/** Colour follows the action, not the direction, so a remapped deck keeps its meaning. */
export const ACTION_TONE: Record<SwipeAction, "good" | "bad" | "accent" | "neutral"> = {
  skip: "bad",
  generate_resume: "good",
  generate_resume_and_cover_letter: "good",
  waitlist: "accent",
  details: "neutral",
  none: "neutral",
};

export const ARROWS: Record<Direction, string> = { left: "←", right: "→", up: "↑", down: "↓" };

/** What the server records for an action, or null when the action only navigates or does nothing. */
export function triageRequest(
  action: SwipeAction,
): { action: "skipped" | "waitlisted" | "accepted"; generate?: "resume" | "resume_and_cover_letter" } | null {
  switch (action) {
    case "skip":
      return { action: "skipped" };
    case "waitlist":
      return { action: "waitlisted" };
    case "generate_resume":
      return { action: "accepted", generate: "resume" };
    case "generate_resume_and_cover_letter":
      return { action: "accepted", generate: "resume_and_cover_letter" };
    default:
      return null;
  }
}
