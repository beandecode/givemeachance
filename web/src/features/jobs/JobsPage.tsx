import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { SearchX, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";

import type { ApplicationStatus, JobSummary } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys } from "@/api/queries";
import {
  Alert,
  Button,
  buttonClass,
  EmptyState,
  ErrorNote,
  Field,
  InlineSelect,
  Input,
  Meta,
  Select,
  SegmentedControl,
} from "@/components/ui";
import { useBackToDeck } from "@/features/discover/useBackToDeck";
import { useScoringBusy } from "./useScoringBusy";
import { useScoringsLeft, useUnscoredCount } from "./useUnscored";
import { useStartTask } from "./useStartTask";
import { Dialog } from "@/components/Dialog";
import { useBreakpoint } from "@/lib/breakpoints";
import { PageHeader } from "@/features/shell/AppShell";
import {
  formatRelative,
  formatSalary,
  recommendationLabel,
  STATUS_LABELS,
  STATUS_ORDER,
  yearsAskedLabel,
} from "@/lib/format";

import { AddJobDialog } from "./AddJobDialog";
import { Score } from "./Score";
import { AdzunaCredit, fromAdzuna } from "./AdzunaCredit";
import { SearchButton } from "./SearchButton";
import { SearchSheet } from "./SearchSheet";
import { StatusText } from "./StatusText";

const PAGE_SIZE = 20;

interface Filters {
  q: string;
  status: ApplicationStatus | "";
  minScore: string;
  sort: "newest" | "score";
  archived: boolean;
  view: View;
}

type View = "all" | "waitlisted" | "skipped" | "unscored";
const VIEWS: { value: View; label: string }[] = [
  { value: "all", label: "All" },
  { value: "waitlisted", label: "Waitlist" },
  { value: "skipped", label: "Skipped" },
  { value: "unscored", label: "Not scored" },
];

function readFilters(params: URLSearchParams): Filters {
  const status = params.get("status") ?? "";
  return {
    q: params.get("q") ?? "",
    status: STATUS_ORDER.includes(status as ApplicationStatus) ? (status as ApplicationStatus) : "",
    minScore: params.get("min_score") ?? "",
    sort: params.get("sort") === "score" ? "score" : "newest",
    archived: params.get("archived") === "1",
    view:
      params.get("view") === "waitlisted" ||
      params.get("view") === "skipped" ||
      params.get("view") === "unscored"
        ? (params.get("view") as View)
        : "all",
  };
}

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function JobsPage() {
  const [params, setParams] = useSearchParams();
  const filters = readFilters(params);
  const [query, setQuery] = useState(filters.q);
  const debouncedQuery = useDebounced(query.trim());
  const [adding, setAdding] = useState(false);
  const [searching, setSearching] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const sidebar = useBreakpoint("xl");
  const inline = useBreakpoint("md");

  useEffect(() => {
    if (debouncedQuery === filters.q) return;
    setParams(
      (current) => {
        if (debouncedQuery) current.set("q", debouncedQuery);
        else current.delete("q");
        return current;
      },
      { replace: true },
    );
  }, [debouncedQuery, filters.q, setParams]);

  const setFilter = (name: string, value: string) =>
    setParams(
      (current) => {
        if (value) current.set(name, value);
        else current.delete(name);
        return current;
      },
      { replace: true },
    );

  const jobs = useInfiniteQuery({
    queryKey: [...keys.jobs, filters],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      unwrap(
        client.GET("/api/v1/jobs", {
          params: {
            query: {
              limit: PAGE_SIZE,
              offset: pageParam,
              sort: filters.sort,
              include_archived: filters.archived,
              ...(filters.view === "waitlisted" || filters.view === "skipped"
                ? { triage: filters.view }
                : {}),
              ...(filters.view === "unscored" ? { scored: false } : {}),
              ...(filters.q ? { q: filters.q } : {}),
              ...(filters.status ? { status: filters.status } : {}),
              ...(filters.minScore ? { min_score: Number(filters.minScore) } : {}),
            },
          },
        }),
      ),
    getNextPageParam: (last) =>
      last.offset + last.items.length < last.total ? last.offset + last.limit : undefined,
  });

  const unscored = useUnscoredCount();
  const preferences = useQuery({
    queryKey: keys.searchPreferences,
    queryFn: () => unwrap(client.GET("/api/v1/search-preferences")),
  });

  const items = jobs.data?.pages.flatMap((page) => page.items) ?? [];
  const total = jobs.data?.pages[0]?.total ?? 0;
  const filtered = Boolean(filters.q || filters.status || filters.minScore || filters.archived);

  const activeFilters = [filters.status, filters.minScore, filters.archived].filter(Boolean).length;

  const filterFields = (
    <div className="flex flex-col gap-4 md:flex-row md:flex-wrap md:items-end xl:flex-col xl:items-stretch">
      <Field label="Status" className="md:min-w-44 xl:min-w-0">
        {(id) => (
          <Select
            id={id}
            value={filters.status}
            onChange={(event) => setFilter("status", event.target.value)}
          >
            <option value="">Any status</option>
            {STATUS_ORDER.map((status) => (
              <option key={status} value={status}>
                {STATUS_LABELS[status]}
              </option>
            ))}
          </Select>
        )}
      </Field>
      {filters.view !== "unscored" && (
        <Field label="Minimum score" className="md:min-w-44 xl:min-w-0">
          {(id) => (
            <Select
              id={id}
              value={filters.minScore}
              onChange={(event) => setFilter("min_score", event.target.value)}
            >
              <option value="">Any score</option>
              <option value="55">55 or more</option>
              <option value="65">65 or more</option>
              <option value="75">75 or more</option>
            </Select>
          )}
        </Field>
      )}
      <label className="flex min-h-11 items-center gap-3 text-secondary">
        <input
          type="checkbox"
          className="size-5 accent-(--color-accent)"
          checked={filters.archived}
          onChange={(event) => setFilter("archived", event.target.checked ? "1" : "")}
        />
        Show archived jobs
      </label>
      {activeFilters > 0 && (
        <Button
          variant="ghost"
          onClick={() => {
            setParams(
              (current) => {
                for (const name of ["status", "min_score", "archived"]) current.delete(name);
                return current;
              },
              { replace: true },
            );
          }}
        >
          Reset filters
        </Button>
      )}
    </div>
  );

  return (
    <>
      <PageHeader
        title="Jobs"
        description={jobs.isSuccess ? `${String(total)} ${total === 1 ? "job" : "jobs"}` : undefined}
        actions={
          <>
            <Button onClick={() => setAdding(true)}>Paste a job</Button>
            <SearchButton />
            <Button
              aria-label="Search options"
              aria-haspopup="dialog"
              title="Search options"
              className="size-11 px-0!"
              icon={<SlidersHorizontal className="size-4" aria-hidden />}
              onClick={() => setSearching(true)}
            />
          </>
        }
      />

      {preferences.data?.source === "default" && (
        <div className="mb-6">
          <Alert tone="accent" title="Tell us what to search for">
            <p>Searches still use the default keywords. Set your roles and location first.</p>
            <Link to="/onboarding" className={`${buttonClass("secondary", "sm")} mt-3`}>
              Finish setup
            </Link>
          </Alert>
        </div>
      )}

      {unscored !== undefined && unscored > 0 && (filters.view === "all" || filters.view === "unscored") && (
        <ScoreAllBanner count={unscored} />
      )}

      <div className="xl:grid xl:grid-cols-[15rem_minmax(0,1fr)] xl:gap-12">
        {sidebar && (
          <aside aria-label="Filters" className="xl:sticky xl:top-24 xl:self-start">
            {filterFields}
          </aside>
        )}
        <div className="max-w-3xl">
          <SegmentedControl
            label="Show"
            className="mb-4"
            options={VIEWS}
            value={filters.view}
            onChange={(view) => setFilter("view", view === "all" ? "" : view)}
          />
          <div className="mb-4 flex gap-2">
            <Input
              className="min-w-0 flex-1"
              type="search"
              aria-label="Search by title or company"
              placeholder="Search title or company"
              value={query}
              maxLength={100}
              onChange={(event) => setQuery(event.target.value)}
            />
            <InlineSelect
              className="w-32 shrink-0 sm:w-40"
              aria-label="Sort"
              value={filters.sort}
              onChange={(event) => setFilter("sort", event.target.value)}
            >
              <option value="newest">Newest</option>
              <option value="score">Best match</option>
            </InlineSelect>
            {!sidebar && (
              <Button
                aria-expanded={inline ? filtersOpen : undefined}
                aria-haspopup={inline ? undefined : "dialog"}
                onClick={() => setFiltersOpen((value) => !value)}
              >
                {activeFilters > 0 ? `Filters (${String(activeFilters)})` : "Filters"}
              </Button>
            )}
          </div>
          {!sidebar && inline && filtersOpen && (
            <div className="glass glass-plate mb-4 rounded-card p-5">{filterFields}</div>
          )}
          {!sidebar && !inline && (
            <Dialog open={filtersOpen} onClose={() => setFiltersOpen(false)} title="Filters">
              {filterFields}
            </Dialog>
          )}

          {jobs.isPending && <ListSkeleton label="Loading jobs" />}
          {jobs.isError && <ErrorNote {...describeError(jobs.error)} />}
          {jobs.isSuccess && items.length === 0 && (
            <EmptyState
              icon={<SearchX className="size-8" aria-hidden />}
              title={
                filtered
                  ? "No jobs match these filters"
                  : filters.view === "waitlisted"
                    ? "Your waitlist is empty"
                    : filters.view === "skipped"
                      ? "Nothing skipped yet"
                      : filters.view === "unscored"
                        ? "Every job is scored"
                        : "No jobs yet"
              }
            >
              {filters.view !== "all" && !filtered ? (
                filters.view === "waitlisted" ? (
                  "Swipe up on a card in Discover to keep a job for later."
                ) : filters.view === "skipped" ? (
                  "Jobs you skip in Discover show up here, so you can bring one back."
                ) : (
                  "Jobs that were added without a score show up here until you score them."
                )
              ) : filtered ? (
                <Button
                  variant="ghost"
                  onClick={() => {
                    setQuery("");
                    setParams({}, { replace: true });
                  }}
                >
                  Clear filters
                </Button>
              ) : (
                "Search the job board with your saved preferences, or paste a job description you found elsewhere."
              )}
            </EmptyState>
          )}

          <ul data-tour="jobs" className="flex flex-col gap-2">
            {items.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </ul>

          {jobs.hasNextPage && (
            <div className="mt-8 flex justify-center">
              <Button busy={jobs.isFetchingNextPage} onClick={() => void jobs.fetchNextPage()}>
                Show more
              </Button>
            </div>
          )}
        </div>
      </div>
      <AddJobDialog open={adding} onClose={() => setAdding(false)} />
      <SearchSheet open={searching} onClose={() => setSearching(false)} />
    </>
  );
}

function ListSkeleton({ label }: { label: string }) {
  return (
    <div role="status" className="flex flex-col gap-2">
      <span className="sr-only">{label}…</span>
      {[0, 1, 2, 3].map((index) => (
        <div key={index} aria-hidden className="h-24 animate-pulse rounded-card bg-subtle" />
      ))}
    </div>
  );
}

function JobRow({ job }: { job: JobSummary }) {
  const salary = formatSalary(job.salary_min, job.salary_max);
  const recommendation = recommendationLabel(job.recommendation_level);
  const years = yearsAskedLabel(job.years_asked_min, job.years_asked_max);
  const place = [job.company || "Unknown company", job.location].filter(Boolean).join(" · ");
  const back = useBackToDeck();
  const busy = useScoringBusy();
  const scoreOne = useStartTask(() =>
    unwrap(client.POST("/api/v1/evaluations/rerun", { body: { scope: "all", job_ids: [job.id] } })),
  );
  const parked = job.triage === "waitlisted" || job.triage === "skipped";
  return (
    <li className="glass group relative flex items-center gap-4 rounded-card px-5 py-4 transition-[filter] duration-(--duration-quick) ease-(--ease-calm) focus-within:ring-2 focus-within:ring-accent hover:brightness-105">
      <div className="min-w-0 flex-1">
        <h2 className="text-subheading font-semibold">
          <Link
            to={`/jobs/${String(job.id)}`}
            className="after:absolute after:inset-0 focus-visible:outline-none"
          >
            {job.title}
          </Link>
        </h2>
        <p className="mt-0.5 truncate text-secondary text-muted">{place}</p>
        <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
          <StatusText status={job.application_status} />
          {recommendation && <Meta>{recommendation}</Meta>}
          {years && <Meta>{years}</Meta>}
          {job.archived_at && <Meta>Archived</Meta>}
          {job.triage === "waitlisted" && <Meta tone="accent">Waitlisted</Meta>}
          {job.triage === "skipped" && <Meta>Skipped</Meta>}
          {job.triage === "accepted" && <Meta tone="good">Résumé requested</Meta>}
          {salary && <Meta className="hidden sm:inline">{salary}</Meta>}
          {fromAdzuna(job) && (
            <span className="relative z-10 text-caption text-muted">
              via <AdzunaCredit className="underline underline-offset-2 hover:text-ink" />
            </span>
          )}
          <Meta className="hidden sm:inline">{formatRelative(job.created_at)}</Meta>
        </p>
      </div>
      {job.match_score === null && (
        <Button
          variant="secondary"
          size="sm"
          className="relative z-10 shrink-0"
          disabled={busy}
          busy={scoreOne.isPending}
          aria-label={`Score ${job.title}`}
          onClick={() => scoreOne.mutate()}
        >
          Score
        </Button>
      )}
      {parked && (
        <Button
          variant="ghost"
          size="sm"
          className="relative z-10 shrink-0"
          busy={back.isPending}
          onClick={() => back.mutate(job.id)}
        >
          Back to Discover
        </Button>
      )}
      <Score score={job.match_score} />
    </li>
  );
}

/** "N jobs aren't scored yet" with one button that scores as many as today's AI limit allows. */
function ScoreAllBanner({ count }: { count: number }) {
  const left = useScoringsLeft();
  const busy = useScoringBusy();
  const limit = Math.min(count, left ?? count, 500);
  const start = useStartTask(() =>
    unwrap(client.POST("/api/v1/evaluations/rerun", { body: { scope: "unscored", limit } })),
  );
  const partial = left !== null && left < count;
  return (
    <div className="glass glass-plate mb-6 flex flex-wrap items-center justify-between gap-3 rounded-card p-4">
      <p className="min-w-0 text-secondary">
        {count} {count === 1 ? "job isn't" : "jobs aren't"} scored yet.
        {left !== null && (
          <span className="text-muted">
            {" "}
            Scoring uses up to {limit} of the {left} AI scorings left today.
          </span>
        )}
      </p>
      <Button
        variant="primary"
        size="sm"
        busy={start.isPending}
        disabled={busy || limit < 1}
        onClick={() => start.mutate()}
      >
        {limit < 1
          ? "No scorings left today"
          : partial
            ? `Score ${String(limit)} now`
            : `Score all ${String(count)}`}
      </Button>
    </div>
  );
}
