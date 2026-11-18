import { useLatestTask } from "@/features/tasks/TaskProvider";
import { isTerminal } from "@/features/tasks/taskCopy";

/** True while a search or a scoring run is working, so a second one is not started on top of it. */
export function useScoringBusy(): boolean {
  return (
    useLatestTask(
      (task) => (task.task_type === "re_evaluate" || task.task_type === "manual_search") && !isTerminal(task),
    ) !== undefined
  );
}
