import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useMemo, useState } from "react";
import { Link } from "react-router";

import type { Schemas } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys, useConfig, useOverview } from "@/api/queries";
import { Dialog } from "@/components/Dialog";
import { Alert, Button, buttonClass, ErrorNote, Field, Select } from "@/components/ui";
import { SearchPreferencesForm } from "@/features/settings/SearchPreferencesForm";

import { SearchSuggestions } from "./SearchSuggestions";

import { useSearchStart } from "./useSearchStart";

type Config = Schemas["JobSearchConfig"];
type Scoring = "all" | "first" | "none";

const FORM_ID = "search-sheet-form";

/** 5, 10, 15 ... up to the server's per-run cap (which is always offered, even if it is not a multiple of 5). */
export function fetchChoices(cap: number): number[] {
  const steps: number[] = [];
  for (let n = 5; n < cap; n += 5) steps.push(n);
  return [...steps, cap];
}

/** How many AI scorings a search may use, from the chosen fetch size and scoring mode. */
export function scoringsFor(mode: Scoring, fetchLimit: number, firstN: number): number {
  if (mode === "none") return 0;
  return mode === "first" ? Math.min(firstN, fetchLimit) : fetchLimit;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

/** Search settings and what to do with the results, in one sheet next to the Search button. */
export function SearchSheet({ open, onClose }: Props) {
  const queryClient = useQueryClient();
  const config = useConfig();
  const overview = useOverview();
  const { state, start } = useSearchStart();
  const preferences = useQuery({
    queryKey: keys.searchPreferences,
    queryFn: () => unwrap(client.GET("/api/v1/search-preferences")),
    enabled: open,
  }).data;
  const demo = config.data?.demo_mode === true;
  const mock = config.data?.llm_provider === "mock";
  const cap = config.data?.search_results_per_run ?? 10;

  const [fetchLimit, setFetchLimit] = useState<number | null>(null);
  const [scoring, setScoring] = useState<Scoring>("all");
  const [firstN, setFirstN] = useState(5);
  const [liveConfig, setLiveConfig] = useState<Config | null>(null);
  const radioName = useId();
  const effectiveFetch = Math.min(fetchLimit ?? cap, cap);
  const choices = useMemo(() => fetchChoices(cap), [cap]);

  const save = useMutation({
    mutationFn: (next: Config) => unwrap(client.PUT("/api/v1/search-preferences", { body: next })),
    onSuccess: async (data) => {
      queryClient.setQueryData(keys.searchPreferences, data);
      await queryClient.invalidateQueries({ queryKey: keys.overview });
    },
  });

  async function submit(next: Config) {
    try {
      await save.mutateAsync(next);
      await start.mutateAsync({
        force: state === "force",
        options: {
          fetch_limit: effectiveFetch,
          score_limit: scoring === "all" ? undefined : scoringsFor(scoring, effectiveFetch, firstN),
        },
      });
      onClose();
    } catch {
      // Both mutations keep their error; it is shown inside the sheet.
    }
  }

  const usage = (provider: string) => overview.data?.usage.find((item) => item.provider === provider);
  const requests = Math.max(1, liveConfig?.adzuna.keywords.length ?? 1);
  const scorings = scoringsFor(scoring, effectiveFetch, firstN);
  const aiLeft = usage("gemini")?.remaining;
  const boardLeft = usage("adzuna")?.remaining;
  const error = save.error ?? start.error;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Search the job board"
      description="Choose what to look for, how many jobs to add and what to do with them."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            form={FORM_ID}
            variant="primary"
            busy={save.isPending || start.isPending}
            disabled={demo || state === "blocked" || state === "loading"}
          >
            Search
          </Button>
        </>
      }
    >
      {preferences ? (
        <div className="flex flex-col gap-6">
          {state === "blocked" && (
            <Alert tone="warn" title="Finish your profile first">
              <Link to="/onboarding" className={`${buttonClass("secondary", "sm")} mt-2`}>
                Go to setup
              </Link>
            </Alert>
          )}
          {demo && <Alert tone="accent">This is a read-only demo, so searching is turned off.</Alert>}
          <SearchSuggestions config={preferences.config} />
          <SearchPreferencesForm
            key={JSON.stringify(preferences.config)}
            initial={preferences.config}
            formId={FORM_ID}
            onSubmitConfig={submit}
            onConfigChange={setLiveConfig}
          />

          <section aria-label="Results" className="flex flex-col gap-4">
            <Field label="How many new jobs to add">
              {(id) => (
                <Select
                  id={id}
                  value={effectiveFetch}
                  onChange={(event) => setFetchLimit(Number(event.target.value))}
                >
                  {choices.map((count) => (
                    <option key={count} value={count}>
                      {count}
                      {count === cap ? " (most per search)" : ""}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-secondary font-medium">After fetching</legend>
              {(
                [
                  ["all", "Score all new jobs"],
                  ["first", "Score only the first few"],
                  ["none", "Only add them, I will score later"],
                ] as [Scoring, string][]
              ).map(([value, label]) => (
                <label key={value} className="flex min-h-11 items-center gap-3 text-secondary">
                  <input
                    type="radio"
                    name={radioName}
                    className="size-5 accent-(--color-accent)"
                    checked={scoring === value}
                    onChange={() => setScoring(value)}
                  />
                  {label}
                  {value === "first" && scoring === "first" && (
                    <input
                      type="number"
                      aria-label="How many to score"
                      min={1}
                      max={effectiveFetch}
                      value={firstN}
                      onChange={(event) =>
                        setFirstN(Math.max(1, Math.min(effectiveFetch, Number(event.target.value) || 1)))
                      }
                      className="glass-plate h-9 w-20 rounded-control border border-line px-2 text-secondary"
                    />
                  )}
                </label>
              ))}
            </fieldset>
            <p className="text-caption text-muted" role="status">
              {mock
                ? "Sample data: no job-board or AI quota is used."
                : `Uses ${String(requests)} job-board ${requests === 1 ? "request" : "requests"}${
                    boardLeft === undefined ? "" : ` (${String(boardLeft)} left today)`
                  } and up to ${String(scorings)} AI ${scorings === 1 ? "scoring" : "scorings"}${
                    aiLeft === undefined ? "" : ` (${String(aiLeft)} left today; retries can use a few more)`
                  }.`}
            </p>
            {!mock && aiLeft !== undefined && scorings > aiLeft && (
              <Alert tone="warn">
                Only {aiLeft} can be scored today. The rest are saved as not scored and you can score them
                later.
              </Alert>
            )}
            {!mock && boardLeft !== undefined && requests > boardLeft && (
              <Alert tone="warn">The job-board limit for today would stop this search part-way.</Alert>
            )}
          </section>
          {error && <ErrorNote {...describeError(error)} />}
        </div>
      ) : (
        <div role="status" className="py-8 text-center text-secondary text-muted">
          Loading your search settings…
        </div>
      )}
    </Dialog>
  );
}
