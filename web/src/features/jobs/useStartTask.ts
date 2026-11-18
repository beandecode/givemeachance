import { useMutation } from "@tanstack/react-query";

import type { Task } from "@/api/client";
import { describeError } from "@/api/errors";
import { useToast } from "@/components/Toaster";
import { useTasks } from "@/features/tasks/TaskProvider";

/** Mutation that starts a background task, follows it, and reports a refused start as a toast. */
export function useStartTask<TVariables = void>(start: (variables: TVariables) => Promise<Task>) {
  const { track } = useTasks();
  const toast = useToast();
  return useMutation({
    mutationFn: start,
    onSuccess: (task) => track(task),
    onError: (error) => {
      const { message, reference } = describeError(error);
      toast({ tone: "error", title: "Couldn't start", description: message, reference });
    },
  });
}
