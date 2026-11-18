import { useMutation, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { X } from "lucide-react";
import { Link, useLocation } from "react-router";

import { client, unwrap } from "@/api/client";
import { keys, useConfig, useJourney } from "@/api/queries";
import { buttonClass } from "@/components/ui";

import { REASON_COPY, STEP_LABELS } from "./journeyCopy";

/** A quiet bar under the header until the first application: where you are and the one thing to do next. */
export function JourneyBar() {
  const demo = useConfig().data?.demo_mode === true;
  const journey = useJourney();
  const queryClient = useQueryClient();
  const pathname = useLocation().pathname;
  const hide = useMutation({
    mutationFn: () => unwrap(client.PUT("/api/v1/journey", { body: { skipped: true } })),
    onSuccess: (data) => queryClient.setQueryData(keys.journey, data),
  });

  const data = journey.data;
  if (!data || data.completed || data.skipped || demo || pathname.startsWith("/onboarding")) return null;
  const current = data.steps.find((step) => step.status === "current");
  if (!current) return null;
  const done = data.steps.filter((step) => step.status === "done").length;

  return (
    <section aria-label="Setup guide" className="glass-plate border-b border-line">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3 md:px-8">
        <ol
          className="flex items-center gap-1"
          aria-label={`Step ${String(done + 1)} of ${String(data.steps.length)}`}
        >
          {data.steps.map((step) => (
            <li
              key={step.key}
              aria-current={step.status === "current" ? "step" : undefined}
              title={STEP_LABELS[step.key]}
              className={clsx(
                "h-1.5 w-6 rounded-full",
                step.status === "done" && "bg-good",
                step.status === "current" && "bg-brand",
                step.status === "todo" && "bg-line-strong",
              )}
            >
              <span className="sr-only">
                {STEP_LABELS[step.key]}: {step.status}
              </span>
            </li>
          ))}
        </ol>
        <p className="min-w-0 flex-1 text-secondary">
          <span className="font-medium">
            Step {done + 1} of {data.steps.length}: {STEP_LABELS[current.key]}.
          </span>{" "}
          <span className="text-muted">
            {(current.reason_code && REASON_COPY[current.reason_code]) ?? ""}
          </span>
        </p>
        <div className="flex items-center gap-1">
          {current.cta_route && (
            <Link to={current.cta_route} className={buttonClass("primary", "sm")}>
              {current.cta_label || "Next"}
            </Link>
          )}
          <button
            type="button"
            onClick={() => hide.mutate()}
            aria-label="Hide the setup guide"
            title="Hide the setup guide"
            className="flex size-11 items-center justify-center rounded-full text-muted hover:bg-subtle hover:text-ink"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
      </div>
    </section>
  );
}
