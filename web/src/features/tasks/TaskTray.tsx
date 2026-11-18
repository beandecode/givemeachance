import { clsx } from "clsx";
import { CircleCheck, CircleX, LoaderCircle, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import type { Task } from "@/api/client";

import { useTasks } from "./TaskProvider";
import { isTerminal, taskDoneTitle, taskFailureMessage, taskStageLabel, taskTitle } from "./taskCopy";

export function ProgressBar({ task }: { task: Task }) {
  const percent =
    task.state === "succeeded" ? 100 : Math.max(task.progress_percent, task.state === "running" ? 5 : 2);
  return (
    <div
      role="progressbar"
      aria-label={taskTitle(task)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      className="h-1.5 w-full overflow-hidden rounded-full bg-subtle"
    >
      <div
        className={clsx(
          "h-full rounded-full transition-[width] duration-500",
          task.state === "failed" || task.state === "expired" ? "bg-bad" : "bg-accent",
        )}
        style={{ width: `${String(percent)}%` }}
      />
    </div>
  );
}

function TaskRow({ task }: { task: Task }) {
  const { cancel, dismiss } = useTasks();
  const done = isTerminal(task);
  return (
    <li className="flex flex-col gap-2 px-4 py-3">
      <div className="flex items-start gap-2">
        {!done && <LoaderCircle className="mt-0.5 size-4 shrink-0 animate-spin text-accent" aria-hidden />}
        {task.state === "succeeded" && (
          <CircleCheck className="mt-0.5 size-4 shrink-0 text-good" aria-hidden />
        )}
        {done && task.state !== "succeeded" && (
          <CircleX className="mt-0.5 size-4 shrink-0 text-bad" aria-hidden />
        )}
        <div className="min-w-0 flex-1 text-sm">
          <p className="font-medium">{task.state === "succeeded" ? taskDoneTitle(task) : taskTitle(task)}</p>
          <p className="text-xs text-muted">
            {done ? (task.state === "succeeded" ? "Done" : taskFailureMessage(task)) : taskStageLabel(task)}
          </p>
          {typeof task.job_id === "number" && (
            <Link
              to={`/jobs/${String(task.job_id)}`}
              className="text-xs font-medium text-accent hover:underline"
            >
              Open job
            </Link>
          )}
        </div>
        {done ? (
          <button
            type="button"
            className="-m-2 inline-flex size-11 items-center justify-center rounded-full text-faint hover:text-ink"
            aria-label="Remove from list"
            onClick={() => dismiss(task.task_id)}
          >
            <X className="size-4" aria-hidden />
          </button>
        ) : (
          !task.cancel_requested && (
            <button
              type="button"
              className="text-xs font-medium text-muted hover:text-bad"
              onClick={() => void cancel(task.task_id)}
            >
              Stop
            </button>
          )
        )}
      </div>
      {!done && <ProgressBar task={task} />}
    </li>
  );
}

/** Header button listing running and recently finished background work. */
export function TaskTray() {
  const { tasks } = useTasks();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const running = tasks.filter((task) => !isTerminal(task)).length;

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (tasks.length === 0) return null;
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex h-11 items-center gap-2 rounded-full px-4 text-secondary font-medium text-muted hover:bg-subtle hover:text-ink"
      >
        {running > 0 ? (
          <LoaderCircle className="size-4 animate-spin text-accent" aria-hidden />
        ) : (
          <CircleCheck className="size-4 text-good" aria-hidden />
        )}
        <span>{running > 0 ? `${String(running)} running` : "Activity"}</span>
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-[min(20rem,calc(100vw-2.5rem))] overflow-hidden rounded-card glass glass-plate shadow-pop">
          <ul className="max-h-96 overflow-y-auto py-2">
            {tasks.map((task) => (
              <TaskRow key={task.task_id} task={task} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
