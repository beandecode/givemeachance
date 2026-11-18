import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys } from "@/api/queries";
import { Button, Field, Input } from "@/components/ui";
import { useToast } from "@/components/Toaster";
import { formatDate } from "@/lib/format";

function inDays(days: number): string {
  const date = new Date(Date.now() + days * 86_400_000);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${String(date.getFullYear())}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Pick the day to follow up on an application (a week from now by default). */
export function FollowUp({
  jobId,
  current,
  overdue,
}: {
  jobId: number;
  current: string | null;
  overdue: boolean;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [day, setDay] = useState(current ?? inDays(7));
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        client.PATCH("/api/v1/jobs/{job_id}/application", {
          params: { path: { job_id: jobId } },
          body: { follow_up_at: day },
        }),
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.job(jobId) }),
        queryClient.invalidateQueries({ queryKey: keys.applications }),
      ]);
    },
    onError: (error) => {
      const { message, reference } = describeError(error);
      toast({ tone: "error", title: "Couldn't save", description: message, reference });
    },
  });

  return (
    <div className="flex flex-col gap-3">
      <p className="font-medium">
        {overdue
          ? `Your follow-up was due ${formatDate(current)}`
          : current
            ? `Follow up on ${formatDate(current)}`
            : "When will you follow up?"}
      </p>
      <Field label="Follow-up date">
        {(id) => <Input id={id} type="date" value={day} onChange={(e) => setDay(e.target.value)} />}
      </Field>
      <Button variant="primary" busy={save.isPending} disabled={!day} onClick={() => save.mutate()}>
        {current ? "Move the date" : "Set follow-up"}
      </Button>
    </div>
  );
}
