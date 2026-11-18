import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { Schemas } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys, useSearchSuggestions } from "@/api/queries";
import { Alert, Button, ErrorNote } from "@/components/ui";

type Config = Schemas["JobSearchConfig"];
type Suggestion = Schemas["SearchSuggestion"];

const LEVEL_NAMES: Record<string, string> = {
  junior: "junior",
  mid: "mid-level",
  senior: "senior",
  staff_plus: "staff and principal",
  management: "management",
};

function describe(suggestion: Suggestion): string {
  return suggestion.kind === "remove_level"
    ? `You skipped ${String(suggestion.count)} jobs as too ${suggestion.value === "junior" ? "junior" : "senior"}. Stop searching ${LEVEL_NAMES[suggestion.value] ?? suggestion.value} jobs?`
    : `You skipped ${String(suggestion.count)} jobs in the wrong field with “${suggestion.value}” in the title. Skip titles with “${suggestion.value}”?`;
}

export function applySuggestion(config: Config, suggestion: Suggestion): Config {
  return suggestion.kind === "remove_level"
    ? { ...config, target_levels: config.target_levels.filter((level) => level !== suggestion.value) }
    : { ...config, exclude_title_words: [...config.exclude_title_words, suggestion.value] };
}

/** Search changes suggested by the reasons you gave for skipping. Nothing changes until you press Apply. */
export function SearchSuggestions({ config }: { config: Config }) {
  const suggestions = useSearchSuggestions();
  const queryClient = useQueryClient();
  const apply = useMutation({
    mutationFn: (suggestion: Suggestion) =>
      unwrap(client.PUT("/api/v1/search-preferences", { body: applySuggestion(config, suggestion) })),
    onSuccess: async (data) => {
      queryClient.setQueryData(keys.searchPreferences, data);
      await queryClient.invalidateQueries({ queryKey: keys.searchSuggestions });
    },
  });

  const items = suggestions.data ?? [];
  if (items.length === 0) return null;
  return (
    <section aria-label="Suggestions" className="flex flex-col gap-3">
      {items.map((suggestion) => (
        <Alert key={`${suggestion.kind}-${suggestion.value}`} tone="accent">
          <p>{describe(suggestion)}</p>
          <Button size="sm" className="mt-2" busy={apply.isPending} onClick={() => apply.mutate(suggestion)}>
            Apply
          </Button>
        </Alert>
      ))}
      {apply.error && <ErrorNote {...describeError(apply.error)} />}
    </section>
  );
}
