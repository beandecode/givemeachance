import type { ApplicationStatus } from "@/api/client";

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  draft: "Saved",
  ready: "Ready to apply",
  submitted: "Applied",
  interview: "Interviewing",
  offer: "Offer",
  hired: "Hired",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export const STATUS_ORDER: ApplicationStatus[] = [
  "draft",
  "ready",
  "submitted",
  "interview",
  "offer",
  "hired",
  "rejected",
  "withdrawn",
];

const PLACEHOLDERS = new Set(["", "unknown", "n/a", "na", "none", "null", "not provided", "not available"]);

/** True for empty values and the "unknown"-style placeholders the profile model may contain. */
export function isBlank(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return PLACEHOLDERS.has(value.trim().toLowerCase());
  if (Array.isArray(value)) return value.every(isBlank);
  return false;
}

export function text(value: unknown): string {
  return typeof value === "string" && !isBlank(value) ? value.trim() : "";
}

export function textList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(text).filter(Boolean) : [];
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value.includes("T") || value.length > 10 ? value : `${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  const seconds = (Date.now() - date.getTime()) / 1000;
  if (Number.isNaN(seconds)) return "";
  if (seconds < 60) return "just now";
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["minute", 60],
    ["hour", 3600],
    ["day", 86400],
    ["month", 2592000],
    ["year", 31536000],
  ];
  let unit: Intl.RelativeTimeFormatUnit = "minute";
  let size = 60;
  for (const [candidate, candidateSize] of units) {
    if (seconds >= candidateSize) {
      unit = candidate;
      size = candidateSize;
    }
  }
  return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(
    -Math.floor(seconds / size),
    unit,
  );
}

export function formatSalary(min: number | null | undefined, max: number | null | undefined): string {
  const fmt = (n: number) =>
    n >= 1000 ? `${String(Math.round(n / 1000))}k` : new Intl.NumberFormat().format(Math.round(n));
  if (min && max) return min === max ? fmt(min) : `${fmt(min)}–${fmt(max)}`;
  if (min) return `from ${fmt(min)}`;
  if (max) return `up to ${fmt(max)}`;
  return "";
}

export type ScoreTone = "good" | "warn" | "bad" | "none";

export function scoreTone(score: number | null | undefined): ScoreTone {
  if (score === null || score === undefined) return "none";
  if (score >= 75) return "good";
  if (score >= 55) return "warn";
  return "bad";
}

export function recommendationLabel(level: string | null | undefined): string {
  switch ((level ?? "").toLowerCase()) {
    case "strong_yes":
      return "Strong match";
    case "yes":
      return "Good match";
    case "maybe":
      return "Possible match";
    case "no":
      return "Weak match";
    default:
      return "";
  }
}

/** "Asks for 5+ years" / "Asks for 3 to 5 years": the experience a posting states, shown next to the score. */
export function yearsAskedLabel(min: number | null | undefined, max: number | null | undefined): string {
  if (min === null || min === undefined) return "";
  if (max !== null && max !== undefined && max > min)
    return `Asks for ${String(min)} to ${String(max)} years`;
  return `Asks for ${String(min)}+ ${min === 1 ? "year" : "years"}`;
}
