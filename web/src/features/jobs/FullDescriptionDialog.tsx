import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { client, unwrap } from "@/api/client";
import { keys } from "@/api/queries";
import { Dialog } from "@/components/Dialog";
import { Button, Field, Textarea } from "@/components/ui";

import { useStartTask } from "./useStartTask";

const MIN_LENGTH = 200;

/** Job boards often return only a short preview. Paste the whole posting and the match is re-scored from it. */
export function FullDescriptionDialog({
  jobId,
  open,
  onClose,
}: {
  jobId: number;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const start = useStartTask(async (description: string) => {
    await unwrap(
      client.PUT("/api/v1/jobs/{job_id}/description", {
        params: { path: { job_id: jobId } },
        body: { description },
      }),
    );
    await queryClient.invalidateQueries({ queryKey: keys.job(jobId) });
    return unwrap(client.POST("/api/v1/evaluations/rerun", { body: { scope: "all", job_ids: [jobId] } }));
  });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Paste the full job description"
      description="The job board only shared a short preview. Paste the whole posting and the match will be scored again."
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          start.mutate(text.trim(), {
            onSuccess: () => {
              setText("");
              onClose();
            },
          });
        }}
        className="grid gap-4"
      >
        <Field label="Job description" hint={`At least ${String(MIN_LENGTH)} characters`}>
          {(id, hint) => (
            <Textarea
              id={id}
              aria-describedby={hint}
              required
              minLength={MIN_LENGTH}
              maxLength={20000}
              rows={12}
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          )}
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" busy={start.isPending}>
            Save and score again
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
