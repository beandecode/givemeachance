import type { DocumentKind } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { useLatestTask } from "@/features/tasks/TaskProvider";
import { isTerminal } from "@/features/tasks/taskCopy";

import { useStartTask } from "./useStartTask";

export const DOCUMENT_NAMES: Record<DocumentKind, string> = {
  resume: "résumé",
  cover_letter: "cover letter",
};

/** Starts (or follows) the background task that writes one document for one job. */
export function useGenerateDocument(jobId: number, kind: DocumentKind) {
  const running = useLatestTask(
    (task) => task.job_id === jobId && task.task_type === `generate_${kind}` && !isTerminal(task),
  );
  const generate = useStartTask(() =>
    unwrap(
      client.POST("/api/v1/jobs/{job_id}/documents", { params: { path: { job_id: jobId } }, body: { kind } }),
    ),
  );
  return { running, generate };
}
