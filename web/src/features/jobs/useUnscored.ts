import { useQuery } from "@tanstack/react-query";

import { client, unwrap } from "@/api/client";
import { keys, useConfig, useOverview } from "@/api/queries";

/** How many of the user's jobs have no match score yet (refreshes with every `["jobs"]` invalidation). */
export function useUnscoredCount(): number | undefined {
  return useQuery({
    queryKey: [...keys.jobs, "unscored-count"],
    queryFn: async () =>
      (await unwrap(client.GET("/api/v1/jobs", { params: { query: { scored: false, limit: 1 } } }))).total,
  }).data;
}

/** AI scorings left today, or null when no daily limit applies (sample data) or it is not known yet. */
export function useScoringsLeft(): number | null {
  const config = useConfig();
  const overview = useOverview();
  if (config.data?.llm_provider === "mock") return null;
  return overview.data?.usage.find((item) => item.provider === "gemini")?.remaining ?? null;
}
