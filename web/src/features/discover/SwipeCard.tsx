import { clsx } from "clsx";
import type { CSSProperties } from "react";

import type { JobDetail, JobSummary } from "@/api/client";
import { formatRelative, formatSalary, recommendationLabel, yearsAskedLabel } from "@/lib/format";

import type { Preferences } from "@/api/client";

import type { SwipeAction } from "./actions";
import { ACTION_LABELS, ACTION_TONE } from "./actions";
import type { Direction } from "./swipe";
import { useSwipe } from "./swipe";

const STAMP_POSITION: Record<Direction, string> = {
  right: "left-4 top-5 -rotate-6",
  left: "right-4 top-5 rotate-6",
  up: "bottom-5 left-1/2 -translate-x-1/2",
  down: "top-5 left-1/2 -translate-x-1/2",
};
const STAMP_TONE = {
  good: "border-good text-good",
  bad: "border-bad text-bad",
  accent: "border-accent text-accent",
  neutral: "border-line-strong text-muted",
} as const;
const EXIT: Record<Direction, CSSProperties> = {
  left: { transform: "translate(-130vw, 0) rotate(-14deg)" },
  right: { transform: "translate(130vw, 0) rotate(14deg)" },
  up: { transform: "translate(0, -120vh)" },
  down: { transform: "translate(0, 120vh)" },
};

function humanize(key: string): string {
  const label = key.replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

/** The next card peeks out behind the front one. */
export function BackCard({ job }: { job: JobSummary }) {
  return (
    <div
      aria-hidden
      className="glass cut-tr absolute inset-0 translate-y-3 scale-[0.96] rounded-card p-5 opacity-70"
    >
      <p className="font-display text-heading">{job.title}</p>
    </div>
  );
}

interface SwipeCardProps {
  job: JobSummary;
  detail: JobDetail | undefined;
  mapping: Preferences["swipe"];
  leaving: Direction | null;
  enabled: boolean;
  allowMouse: boolean;
  onCommit: (direction: Direction) => void;
}

/** The front card: drag it (touch, pen, optionally mouse) and a stamp names what releasing will do. */
export function SwipeCard({ job, detail, mapping, leaving, enabled, allowMouse, onCommit }: SwipeCardProps) {
  const swipe = useSwipe({ enabled: enabled && leaving === null, allowMouse, onCommit });
  const hint = leaving ?? swipe.hint;
  const match = detail?.match ?? null;
  const reasons = [...(match?.match_reasons ?? []), ...(match?.strengths ?? [])].slice(0, 2);
  const gap = match?.gaps[0];
  const salary = formatSalary(job.salary_min, job.salary_max);
  const years = yearsAskedLabel(job.years_asked_min, job.years_asked_max);
  const style: CSSProperties = leaving
    ? { ...EXIT[leaving], transition: "transform 230ms ease-in" }
    : swipe.style;

  return (
    <article
      data-tour="deck"
      aria-label={`${job.title} at ${job.company}`}
      {...swipe.handlers}
      style={style}
      className={clsx(
        "glass cut-tr hud absolute inset-0 flex touch-none flex-col gap-3 overflow-hidden rounded-card p-5 select-none",
        enabled && "cursor-grab active:cursor-grabbing",
      )}
    >
      {(Object.keys(STAMP_POSITION) as Direction[]).map((direction) => {
        const action: SwipeAction = mapping[direction];
        if (action === "none") return null;
        return (
          <span
            key={direction}
            aria-hidden
            className={clsx(
              "glass-plate pointer-events-none absolute z-10 rounded-control border-[3px] px-3 py-1 font-display text-subheading tracking-wide whitespace-nowrap uppercase transition-opacity duration-(--duration-quick)",
              STAMP_POSITION[direction],
              STAMP_TONE[ACTION_TONE[action]],
              hint === direction ? "opacity-100" : "opacity-0",
            )}
          >
            {ACTION_LABELS[action]}
          </span>
        );
      })}

      <p className="font-mono text-caption text-muted">
        {job.company} · {formatRelative(job.created_at)}
      </p>
      <h2 className="font-display text-heading leading-tight text-balance">{job.title}</h2>
      <p className="flex flex-wrap gap-x-3 text-caption text-muted">
        <span>{job.location}</span>
        {salary && <span>{salary}</span>}
      </p>

      <div className="flex flex-wrap items-end gap-x-3 gap-y-1">
        <span
          role="img"
          aria-label={`Match score ${String(job.match_score ?? 0)} out of 100`}
          className="cut-tr bg-brand px-3 py-1 font-display text-figure leading-none text-on-brand"
        >
          {job.match_score ?? "–"}
        </span>
        <span className="pb-1 font-display text-caption tracking-wide text-muted uppercase">
          {recommendationLabel(job.recommendation_level)}
        </span>
        {years && <span className="pb-1 text-caption text-muted">{years}</span>}
      </div>

      <div className="glass-plate flex flex-1 flex-col gap-3 overflow-hidden rounded-control p-3">
        {match ? (
          <>
            <ul className="grid gap-1.5">
              {Object.entries(match.dimension_scores)
                .slice(0, 4)
                .map(([key, value]) => (
                  <li key={key} className="grid grid-cols-[6.5rem_1fr_2rem] items-center gap-2 text-caption">
                    <span className="truncate text-muted">{humanize(key)}</span>
                    <span aria-hidden className="h-1.5 overflow-hidden rounded-full bg-line">
                      <span
                        className="block h-full rounded-full bg-accent"
                        style={{ width: `${String(value)}%` }}
                      />
                    </span>
                    <span className="text-right font-mono">{value}</span>
                  </li>
                ))}
            </ul>
            <ul className="grid gap-1 text-caption">
              {reasons.map((reason) => (
                <li
                  key={reason}
                  className="relative pl-4 before:absolute before:left-0 before:text-good before:content-['+']"
                >
                  {reason}
                </li>
              ))}
              {gap && (
                <li className="relative pl-4 before:absolute before:left-0 before:text-bad before:content-['–']">
                  {gap}
                </li>
              )}
            </ul>
          </>
        ) : (
          <p className="text-caption text-muted">Loading the match details…</p>
        )}
      </div>
    </article>
  );
}
