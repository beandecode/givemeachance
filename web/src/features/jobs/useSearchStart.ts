import { client, unwrap } from "@/api/client";
import { useOverview } from "@/api/queries";
import { useLatestTask } from "@/features/tasks/TaskProvider";
import { isTerminal } from "@/features/tasks/taskCopy";

import { useStartTask } from "./useStartTask";

export interface SearchOptions {
  fetch_limit?: number;
  score_limit?: number;
}

/**
 * Starting a job-board search, shared by the one-click button and the search sheet.
 * `state` follows the profile gate: `blocked` (finish setup first), `force` (only optional details are missing, so the
 * user may search anyway), `ready`, or `loading`.
 */
export function useSearchStart() {
  const overview = useOverview();
  const running = useLatestTask((task) => task.task_type === "manual_search" && !isTerminal(task));
  const start = useStartTask(({ force, options }: { force: boolean; options?: SearchOptions }) =>
    unwrap(client.POST("/api/v1/searches", { body: { force_when_high_missing: force, ...options } })),
  );
  const readiness = overview.data?.readiness;
  let state: "loading" | "blocked" | "force" | "ready" = "ready";
  if (!readiness) state = "loading";
  else if (!readiness.allowed) {
    state =
      readiness.review_status === "approved" && readiness.high_priority_missing_count > 0
        ? "force"
        : "blocked";
  }
  return { state, running: running !== undefined, start };
}
