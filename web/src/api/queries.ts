import { useQuery } from "@tanstack/react-query";

import { client, unwrap } from "./client";

/** Query keys. Invalidating a prefix (e.g. ["jobs"]) refreshes every query below it. */
export const keys = {
  session: ["session"] as const,
  config: ["config"] as const,
  overview: ["overview"] as const,
  journey: ["journey"] as const,
  profile: ["profile"] as const,
  profileVersions: ["profile", "versions"] as const,
  jobs: ["jobs"] as const,
  job: (id: number) => ["job", id] as const,
  jobDocuments: (id: number) => ["job", id, "documents"] as const,
  document: (kind: string, id: number) => ["document", kind, id] as const,
  applications: ["applications"] as const,
  preferences: ["preferences"] as const,
  deck: (minScore: number) => ["jobs", "deck", minScore] as const,
  acceptedJobs: ["jobs", "accepted"] as const,
  searchPreferences: ["search-preferences"] as const,
  suggestedPreferences: ["search-preferences", "suggested"] as const,
  searchSuggestions: ["search-suggestions"] as const,
  activeTasks: ["tasks", "active"] as const,
  task: (taskId: string) => ["task", taskId] as const,
};

export function useSession() {
  return useQuery({
    queryKey: keys.session,
    queryFn: () => unwrap(client.GET("/api/v1/session")),
    staleTime: 60_000,
  });
}

export function useConfig() {
  return useQuery({
    queryKey: keys.config,
    queryFn: () => unwrap(client.GET("/api/v1/config")),
    staleTime: Infinity,
  });
}

export function useOverview() {
  return useQuery({
    queryKey: keys.overview,
    queryFn: () => unwrap(client.GET("/api/v1/overview")),
  });
}

export function useProfile() {
  return useQuery({
    queryKey: keys.profile,
    queryFn: () => unwrap(client.GET("/api/v1/profile")),
  });
}

export function usePreferences() {
  return useQuery({
    queryKey: keys.preferences,
    queryFn: () => unwrap(client.GET("/api/v1/preferences")),
    staleTime: 60_000,
  });
}

export function useJourney() {
  return useQuery({
    queryKey: keys.journey,
    queryFn: () => unwrap(client.GET("/api/v1/journey")),
    staleTime: 5_000,
  });
}

export function useSearchSuggestions(enabled = true) {
  return useQuery({
    queryKey: keys.searchSuggestions,
    queryFn: () => unwrap(client.GET("/api/v1/search-suggestions")),
    enabled,
  });
}
