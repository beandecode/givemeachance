import { clsx } from "clsx";
import { Check } from "lucide-react";

import { JOB_STEP_LABELS, type JobJourney } from "./journeyCopy";

/** The five steps of one job: score, write, check, apply, follow up. */
export function JobSteps({ journey }: { journey: JobJourney }) {
  return (
    <ol aria-label="Steps for this job" className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2">
      {journey.steps.map((step) => {
        const attention = step.key === "review" && step.reason_code === "document_warnings";
        const done = step.status === "done";
        return (
          <li
            key={step.key}
            aria-current={step.status === "current" ? "step" : undefined}
            className={clsx(
              "flex items-center gap-1.5 text-secondary",
              step.status === "current" ? "font-semibold text-ink" : "text-muted",
              attention && "text-warn",
            )}
          >
            <span
              aria-hidden
              className={clsx(
                "flex size-5 items-center justify-center rounded-full border text-caption",
                done && "border-good bg-good-soft text-good",
                step.status === "current" && "border-brand bg-brand text-on-brand",
                !done && step.status !== "current" && "border-line-strong",
                attention && "border-warn",
              )}
            >
              {done && <Check className="size-3" />}
            </span>
            {JOB_STEP_LABELS[step.key]}
            <span className="sr-only">
              {done ? " (done)" : step.status === "current" ? " (next)" : attention ? " (needs a look)" : ""}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
