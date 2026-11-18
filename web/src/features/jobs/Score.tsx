import { clsx } from "clsx";

import { scoreTone } from "@/lib/format";

const TONE_RING = {
  good: "stroke-accent",
  warn: "stroke-warn",
  bad: "stroke-bad",
  none: "stroke-line",
} as const;

type ScoreVariant = "row" | "compact" | "hero";

/** The match score as a large serif number ("—" until the job is scored). `hero` adds a thin ring. */
export function Score({
  score,
  variant = "row",
}: {
  score: number | null | undefined;
  variant?: ScoreVariant;
}) {
  const tone = scoreTone(score);
  const label =
    score === null || score === undefined ? "Not scored yet" : `Match score ${String(score)} out of 100`;

  if (variant !== "hero") {
    return (
      <span
        role="img"
        aria-label={label}
        className={clsx(
          "cut-tr inline-flex shrink-0 items-center justify-center px-2.5 py-1 font-display leading-none",
          variant === "row" ? "min-w-14 text-[1.625rem]" : "min-w-12 text-[1.25rem]",
          tone === "none" ? "bg-subtle text-faint" : "bg-brand text-on-brand",
        )}
      >
        {score ?? "—"}
      </span>
    );
  }

  const radius = 45;
  const circumference = 2 * Math.PI * radius;
  return (
    <div role="img" aria-label={label} className="relative size-28 shrink-0">
      <svg viewBox="0 0 100 100" className="size-full -rotate-90" aria-hidden>
        <circle cx="50" cy="50" r={radius} fill="none" strokeWidth="3" className="stroke-subtle" />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          strokeWidth="3"
          strokeLinecap="round"
          className={TONE_RING[tone]}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - (score ?? 0) / 100)}
        />
      </svg>
      <span
        className={clsx(
          "absolute inset-0 flex items-center justify-center font-display text-figure leading-none",
          tone === "none" ? "text-faint" : "text-ink",
        )}
      >
        {score ?? "—"}
      </span>
    </div>
  );
}
