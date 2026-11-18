import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { keys } from "@/api/queries";

export function createQueryClient(): QueryClient {
  // Any 401 means the session ended: drop the cached user so <RequireAuth> sends us to sign-in.
  const onError = (error: unknown) => {
    if (error instanceof ApiError && error.status === 401) {
      queryClient.setQueryData(keys.session, { user: null });
    }
  };
  const queryClient: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({
      onError,
      // Saving anything may complete a step of the setup guide.
      onSuccess: () => void queryClient.invalidateQueries({ queryKey: keys.journey }),
    }),
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        retry: (failureCount, error) =>
          !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failureCount < 2,
        refetchOnWindowFocus: true,
      },
      mutations: { retry: false },
    },
  });
  return queryClient;
}
