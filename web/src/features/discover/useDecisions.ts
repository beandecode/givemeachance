import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { JobPage, JobSummary } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys } from "@/api/queries";
import { useToast } from "@/components/Toaster";
import { useTasks } from "@/features/tasks/TaskProvider";

import type { SwipeAction } from "./actions";
import { ACTION_LABELS, triageRequest } from "./actions";

export type TriageRequest = NonNullable<ReturnType<typeof triageRequest>>;

interface HistoryEntry {
  job: JobSummary;
  action: SwipeAction;
}

const HISTORY_LIMIT = 20;

/** Records swipe decisions with an instant, optimistic removal from the deck, and undoes the last ones. */
export function useDecisions(minScore: number) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { track } = useTasks();
  const deckKey = keys.deck(minScore);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  function removeFromDeck(jobId: number) {
    queryClient.setQueryData<JobPage>(deckKey, (page) =>
      page
        ? {
            ...page,
            items: page.items.filter((item) => item.id !== jobId),
            total: Math.max(0, page.total - 1),
          }
        : page,
    );
  }
  function restoreToDeck(job: JobSummary) {
    queryClient.setQueryData<JobPage>(deckKey, (page) =>
      page && !page.items.some((item) => item.id === job.id)
        ? { ...page, items: [job, ...page.items], total: page.total + 1 }
        : page,
    );
  }
  function refreshOtherLists() {
    void queryClient.invalidateQueries({
      queryKey: keys.jobs,
      predicate: (query) => query.queryKey[1] !== "deck",
    });
    void queryClient.invalidateQueries({ queryKey: keys.applications });
  }

  const decide = useMutation({
    mutationFn: ({ job, request }: { job: JobSummary; action: SwipeAction; request: TriageRequest }) =>
      unwrap(
        client.PUT("/api/v1/jobs/{job_id}/triage", { params: { path: { job_id: job.id } }, body: request }),
      ),
    onMutate: ({ job }) => removeFromDeck(job.id),
    onSuccess: (result, { job, action }) => {
      result.tasks.forEach(track);
      if (result.queued_for_later) {
        toast({
          tone: "info",
          title: "Waiting for a free slot",
          description:
            "Three documents are already being written. This one starts as soon as a slot is free.",
        });
      }
      setHistory((entries) => [...entries.slice(-(HISTORY_LIMIT - 1)), { job, action }]);
      refreshOtherLists();
    },
    onError: (error, { job }) => {
      restoreToDeck(job);
      const { message, reference } = describeError(error);
      toast({ tone: "error", title: "Couldn't save that decision", description: message, reference });
    },
  });

  const undo = useMutation({
    mutationFn: (entry: HistoryEntry) =>
      unwrap(client.DELETE("/api/v1/jobs/{job_id}/triage", { params: { path: { job_id: entry.job.id } } })),
    onSuccess: (_detail, entry) => {
      restoreToDeck(entry.job);
      setHistory((entries) => entries.filter((candidate) => candidate !== entry));
      refreshOtherLists();
      toast({ tone: "info", title: `Undid “${ACTION_LABELS[entry.action]}”` });
    },
    onError: (error) => {
      const { message, reference } = describeError(error);
      toast({ tone: "error", title: "Couldn't undo", description: message, reference });
    },
  });

  return { decide, undo, last: history[history.length - 1] };
}
