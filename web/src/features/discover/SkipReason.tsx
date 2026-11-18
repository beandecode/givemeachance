import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { JobSummary } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { keys } from "@/api/queries";

const REASONS = [
  ["too_senior", "Too senior"],
  ["too_junior", "Too junior"],
  ["wrong_field", "Wrong field"],
  ["location", "Location"],
  ["pay", "Pay"],
  ["other", "Other"],
] as const;

type Reason = (typeof REASONS)[number][0];

/** After a skip: an optional one-tap reason. Repeated reasons turn into search suggestions. */
export function SkipReason({ job }: { job: JobSummary }) {
  const queryClient = useQueryClient();
  const [chosen, setChosen] = useState<Reason | null>(null);
  const save = useMutation({
    mutationFn: (reason: Reason) =>
      unwrap(
        client.PUT("/api/v1/jobs/{job_id}/triage", {
          params: { path: { job_id: job.id } },
          body: { action: "skipped", reason },
        }),
      ),
    onSuccess: (_result, reason) => {
      setChosen(reason);
      void queryClient.invalidateQueries({ queryKey: keys.searchSuggestions });
    },
  });

  return (
    <section aria-label="Why did you skip this job?" className="mb-6 flex flex-wrap items-center gap-2">
      <p className="text-secondary text-muted">
        {chosen ? "Thanks, noted." : `Why skip ${job.title}? Optional:`}
      </p>
      {!chosen &&
        REASONS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            disabled={save.isPending}
            onClick={() => save.mutate(value)}
            className="glass-ctl h-11 rounded-full px-4 text-secondary text-ink hover:brightness-95 disabled:opacity-50"
          >
            {label}
          </button>
        ))}
    </section>
  );
}
