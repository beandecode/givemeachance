import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";

import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { Button } from "@/components/ui";
import { useToast } from "@/components/Toaster";

export function useReviewProfile() {
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (input: { profileId: number; status: "approved" | "needs_changes" }) =>
      unwrap(
        client.POST("/api/v1/profile/{profile_id}/review", {
          params: { path: { profile_id: input.profileId } },
          body: { review_status: input.status, review_note: "" },
        }),
      ),
    onSuccess: async (_, input) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["profile"] }),
        queryClient.invalidateQueries({ queryKey: ["overview"] }),
      ]);
      toast({
        tone: "success",
        title: input.status === "approved" ? "Profile approved" : "Marked as needing changes",
      });
    },
    onError: (error) => {
      const { message, reference } = describeError(error);
      toast({ tone: "error", title: "Couldn't save the review", description: message, reference });
    },
  });
}

export function ApproveButton({ profileId, onApproved }: { profileId: number; onApproved?: () => void }) {
  const review = useReviewProfile();
  return (
    <Button
      variant="primary"
      icon={<Check className="size-4" aria-hidden />}
      busy={review.isPending}
      onClick={() => review.mutate({ profileId, status: "approved" }, { onSuccess: () => onApproved?.() })}
    >
      Looks right, approve
    </Button>
  );
}
