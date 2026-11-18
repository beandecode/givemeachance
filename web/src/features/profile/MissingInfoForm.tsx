import { useState } from "react";

import { client, unwrap } from "@/api/client";
import { Button, Dot, Field, Textarea } from "@/components/ui";
import { useStartTask } from "@/features/jobs/useStartTask";
import { useLatestTask } from "@/features/tasks/TaskProvider";
import { isTerminal } from "@/features/tasks/taskCopy";

import type { MissingItem } from "./profileModel";

const PRIORITY_TONE = { high: "bad", medium: "warn", low: "neutral" } as const;

/** Answer the profile's open questions; the answers produce a new version for review. */
export function MissingInfoForm({ profileId, items }: { profileId: number; items: MissingItem[] }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const running = useLatestTask((task) => task.task_type === "supplement_profile" && !isTerminal(task));
  const answered = Object.entries(answers).filter(([, value]) => value.trim());
  const start = useStartTask(() =>
    unwrap(
      client.POST("/api/v1/profile/supplement", {
        body: {
          profile_id: profileId,
          selected_fields: answered.map(([field]) => field),
          answers: Object.fromEntries(answered.map(([field, value]) => [field, value.trim()])),
        },
      }),
    ),
  );

  if (items.length === 0) return null;
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        start.mutate(undefined, { onSuccess: () => setAnswers({}) });
      }}
    >
      {items.map((item) => (
        <Field key={`${item.field}:${item.question}`} label={item.question}>
          {(id) => (
            <div className="flex flex-col gap-1.5">
              <Dot tone={PRIORITY_TONE[item.priority]} className="self-start">
                {item.priority === "high"
                  ? "Needed to search"
                  : item.priority === "medium"
                    ? "Helpful"
                    : "Optional"}
              </Dot>
              <Textarea
                id={id}
                rows={2}
                value={answers[item.field] ?? ""}
                onChange={(event) =>
                  setAnswers((current) => ({ ...current, [item.field]: event.target.value }))
                }
              />
            </div>
          )}
        </Field>
      ))}
      <div className="flex justify-end">
        <Button
          type="submit"
          variant="primary"
          busy={start.isPending || running !== undefined}
          disabled={answered.length === 0}
        >
          {running ? "Updating profile…" : "Add answers to profile"}
        </Button>
      </div>
    </form>
  );
}
