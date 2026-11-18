import type { QueryKey } from "@tanstack/react-query";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";

import type { Task } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { keys } from "@/api/queries";
import { useToast } from "@/components/Toaster";

import { isTerminal, taskDoneTitle, taskFailureMessage, taskTitle } from "./taskCopy";
import { fetchTaskResult, RESULT_NOTICES } from "./taskResults";

const POLL_MS = 1500;

/** What to refresh when a task of each type finishes. */
const INVALIDATES: Record<string, QueryKey[]> = {
  generate_resume: [["job"], ["jobs"], ["applications"], ["overview"]],
  generate_cover_letter: [["job"], ["jobs"], ["applications"], ["overview"]],
  manual_search: [["jobs"], ["job"], ["applications"], ["overview"]],
  manual_jd_match: [["jobs"], ["job"], ["applications"], ["overview"]],
  re_evaluate: [["jobs"], ["job"], ["applications"], ["overview"]],
  synthesize_profile: [["profile"], ["overview"], ["search-preferences"]],
  supplement_profile: [["profile"], ["overview"], ["search-preferences"]],
};

interface TaskContextValue {
  /** Latest snapshot of every task this tab is following, newest first. */
  tasks: Task[];
  /** Start following a task returned by a 202 response. */
  track: (task: Task) => void;
  cancel: (taskId: string) => Promise<void>;
  dismiss: (taskId: string) => void;
}

const TaskContext = createContext<TaskContextValue | null>(null);

export function TaskProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [ids, setIds] = useState<string[]>([]);
  const notified = useRef(new Set<string>());

  const track = useCallback(
    (task: Task) => {
      queryClient.setQueryData(keys.task(task.task_id), task);
      setIds((current) => (current.includes(task.task_id) ? current : [task.task_id, ...current]));
    },
    [queryClient],
  );

  // After a reload, pick up whatever is still queued or running.
  const active = useQuery({
    queryKey: keys.activeTasks,
    queryFn: () => unwrap(client.GET("/api/v1/tasks", { params: { query: { active: true, limit: 50 } } })),
    staleTime: Infinity,
  });
  useEffect(() => {
    active.data?.items.forEach((task) => {
      notified.current.delete(task.task_id);
      track(task);
    });
  }, [active.data, track]);

  const results = useQueries({
    queries: ids.map((taskId) => ({
      queryKey: keys.task(taskId),
      queryFn: () => unwrap(client.GET("/api/v1/tasks/{task_id}", { params: { path: { task_id: taskId } } })),
      refetchInterval: (query: { state: { data: Task | undefined } }) =>
        query.state.data && isTerminal(query.state.data) ? false : POLL_MS,
      refetchIntervalInBackground: true,
    })),
  });

  const tasks = useMemo(
    () => results.map((result) => result.data).filter((task): task is Task => task !== undefined),
    [results],
  );

  useEffect(() => {
    for (const task of tasks) {
      if (!isTerminal(task) || notified.current.has(task.task_id)) continue;
      notified.current.add(task.task_id);
      for (const key of [...(INVALIDATES[task.task_type] ?? []), keys.journey]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
      if (task.state === "succeeded") {
        const notice = RESULT_NOTICES[task.task_type];
        if (notice) {
          // Say what the task did (counts, what was left unscored); fall back to the plain title if that fails.
          void fetchTaskResult(task.task_id)
            .then((raw) => {
              const { title, description, tone, notScored } = notice(raw);
              toast({
                tone: tone === "info" ? "info" : "success",
                title,
                ...(description ? { description } : {}),
                ...(notScored > 0
                  ? { action: { label: "Show", onClick: () => void navigate("/jobs?view=unscored") } }
                  : {}),
              });
            })
            .catch(() => toast({ tone: "success", title: taskDoneTitle(task) }));
        } else {
          toast({ tone: "success", title: taskDoneTitle(task) });
        }
      } else if (task.state !== "cancelled") {
        toast({
          tone: "error",
          title: `${taskTitle(task)} didn't finish`,
          description: taskFailureMessage(task),
          reference: task.correlation_id,
        });
      }
    }
  }, [tasks, queryClient, toast, navigate]);

  const cancel = useCallback(
    async (taskId: string) => {
      const task = await unwrap(
        client.POST("/api/v1/tasks/{task_id}/cancel", { params: { path: { task_id: taskId } } }),
      );
      queryClient.setQueryData(keys.task(taskId), task);
    },
    [queryClient],
  );

  const dismiss = useCallback((taskId: string) => {
    setIds((current) => current.filter((id) => id !== taskId));
  }, []);

  const value = useMemo(() => ({ tasks, track, cancel, dismiss }), [tasks, track, cancel, dismiss]);
  return <TaskContext.Provider value={value}>{children}</TaskContext.Provider>;
}

export function useTasks(): TaskContextValue {
  const context = useContext(TaskContext);
  if (!context) throw new Error("useTasks must be used inside <TaskProvider>");
  return context;
}

/** The most recent followed task matching `predicate` (e.g. generation for one job), finished or not. */
export function useLatestTask(predicate: (task: Task) => boolean): Task | undefined {
  const { tasks } = useTasks();
  return tasks.find(predicate);
}
