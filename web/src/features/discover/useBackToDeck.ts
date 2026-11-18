import { useMutation, useQueryClient } from "@tanstack/react-query";

import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys } from "@/api/queries";
import { useToast } from "@/components/Toaster";

/** Takes a waitlisted or skipped job out of that list so it shows up in Discover again. */
export function useBackToDeck() {
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (jobId: number) =>
      unwrap(client.DELETE("/api/v1/jobs/{job_id}/triage", { params: { path: { job_id: jobId } } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.jobs });
      void queryClient.invalidateQueries({ queryKey: ["job"] });
      toast({ tone: "success", title: "Back in Discover" });
    },
    onError: (error) => {
      const { message, reference } = describeError(error);
      toast({ tone: "error", title: "Couldn't move it back", description: message, reference });
    },
  });
}
