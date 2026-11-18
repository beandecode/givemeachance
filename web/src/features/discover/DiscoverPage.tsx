import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, FileStack, FileText, Info, Undo2, X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import type { JobSummary } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys, useJourney, usePreferences } from "@/api/queries";
import { Button, ErrorNote, Spinner } from "@/components/ui";
import { DiscoverEmpty } from "@/features/journey/DiscoverEmpty";
import { PageHeader } from "@/features/shell/AppShell";
import { useTasks } from "@/features/tasks/TaskProvider";
import { isTerminal } from "@/features/tasks/taskCopy";
import { useUnscoredCount } from "@/features/jobs/useUnscored";
import { useBreakpoint } from "@/lib/breakpoints";

import type { SwipeAction } from "./actions";
import { ACTION_LABELS, ARROWS, DEFAULT_PREFERENCES, triageRequest } from "./actions";
import { BackCard, SwipeCard } from "./SwipeCard";
import type { Direction } from "./swipe";
import { DIRECTIONS } from "./swipe";
import { SkipReason } from "./SkipReason";
import { useDecisions } from "./useDecisions";
import { AdzunaCredit, fromAdzuna } from "@/features/jobs/AdzunaCredit";

const ICONS: Record<SwipeAction, ReactNode> = {
  skip: <X className="size-5" aria-hidden />,
  generate_resume: <FileText className="size-5" aria-hidden />,
  generate_resume_and_cover_letter: <FileStack className="size-5" aria-hidden />,
  waitlist: <Bookmark className="size-5" aria-hidden />,
  details: <Info className="size-5" aria-hidden />,
  none: null,
};
const EXIT_MS = 230;
/** Same limit as the server: documents waiting for a free slot are started one at a time. */
const MAX_ACTIVE_TASKS = 3;

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

export function DiscoverPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const wide = useBreakpoint("lg");
  const { tasks, track } = useTasks();
  const preferences = usePreferences();
  const prefs = preferences.data ?? DEFAULT_PREFERENCES;
  const minScore = prefs.deck.min_score;
  const { decide, undo, last } = useDecisions(minScore);
  const unscored = useUnscoredCount();
  const journey = useJourney();
  const [leaving, setLeaving] = useState<Direction | null>(null);
  const busy = useRef(false);

  const deck = useQuery({
    queryKey: keys.deck(minScore),
    queryFn: () =>
      unwrap(
        client.GET("/api/v1/jobs", {
          params: { query: { triage: "pending", min_score: minScore, sort: "score", limit: 50 } },
        }),
      ),
    enabled: !preferences.isPending,
    refetchOnWindowFocus: false,
  });
  const items = useMemo(() => deck.data?.items ?? [], [deck.data]);
  const front = items[0];
  const next = items[1];

  const frontDetail = useQuery({
    queryKey: keys.job(front?.id ?? 0),
    queryFn: () =>
      unwrap(client.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: front?.id ?? 0 } } })),
    enabled: front !== undefined,
  });
  useEffect(() => {
    for (const job of items.slice(1, 3)) {
      void queryClient
        .query({
          queryKey: keys.job(job.id),
          queryFn: () =>
            unwrap(client.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: job.id } } })),
        })
        .catch(() => undefined);
    }
  }, [items, queryClient]);

  // Documents that were accepted while the task limit was full start when a slot frees up (once each per visit).
  const accepted = useQuery({
    queryKey: keys.acceptedJobs,
    queryFn: () =>
      unwrap(client.GET("/api/v1/jobs", { params: { query: { triage: "accepted", limit: 100 } } })),
  });
  const attempted = useRef(new Set<number>());
  const waiting = useMemo(
    () =>
      (accepted.data?.items ?? []).filter(
        (job) =>
          job.triage_generate !== null &&
          (!job.has_resume || (job.triage_generate === "resume_and_cover_letter" && !job.has_cover_letter)) &&
          !tasks.some((task) => task.job_id === job.id),
      ),
    [accepted.data, tasks],
  );
  const activeCount = tasks.filter((task) => !isTerminal(task)).length;
  useEffect(() => {
    if (activeCount >= MAX_ACTIVE_TASKS) return;
    const job = waiting.find((candidate) => !attempted.current.has(candidate.id));
    if (!job?.triage_generate) return;
    attempted.current.add(job.id);
    void unwrap(
      client.PUT("/api/v1/jobs/{job_id}/triage", {
        params: { path: { job_id: job.id } },
        body: { action: "accepted", generate: job.triage_generate },
      }),
    )
      .then((result) => result.tasks.forEach(track))
      .catch(() => undefined);
  }, [waiting, activeCount, track]);

  function commit(direction: Direction) {
    if (!front || busy.current) return;
    const action = prefs.swipe[direction];
    if (action === "none") return;
    if (action === "details") {
      void navigate(`/jobs/${String(front.id)}`, { state: { from: "discover" } });
      return;
    }
    const request = triageRequest(action);
    if (!request) return;
    busy.current = true;
    setLeaving(direction);
    window.setTimeout(
      () => {
        setLeaving(null);
        busy.current = false;
        decide.mutate({ job: front, action, request });
      },
      prefersReducedMotion() ? 0 : EXIT_MS,
    );
  }

  // Arrow keys always work; U undoes the last decision.
  const commitRef = useRef(commit);
  const undoRef = useRef<() => void>(() => undefined);
  useEffect(() => {
    commitRef.current = commit;
    undoRef.current = () => {
      if (last && !undo.isPending) undo.mutate(last);
    };
  });
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      if (document.querySelector("dialog[open]")) return;
      const map: Record<string, Direction> = {
        ArrowLeft: "left",
        ArrowRight: "right",
        ArrowUp: "up",
        ArrowDown: "down",
      };
      const direction = map[event.key];
      if (direction) {
        event.preventDefault();
        commitRef.current(direction);
      } else if (event.key.toLowerCase() === "u") {
        undoRef.current();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (preferences.isPending || deck.isPending) return <Spinner label="Loading your deck" />;
  if (deck.isError) return <ErrorNote {...describeError(deck.error)} />;

  const directionsInUse = DIRECTIONS.filter((direction) => prefs.swipe[direction] !== "none");
  const total = deck.data.total;

  return (
    <>
      <PageHeader
        title="Discover"
        description={
          total === 0
            ? undefined
            : `${String(total)} new ${total === 1 ? "job" : "jobs"} at ${String(minScore)} or above`
        }
        actions={
          last && (
            <Button
              variant="secondary"
              icon={<Undo2 className="size-4" aria-hidden />}
              busy={undo.isPending}
              onClick={() => undoRef.current()}
            >
              Undo
            </Button>
          )
        }
      />
      {unscored !== undefined && unscored > 0 && (
        <p className="mb-6 text-secondary text-muted">
          {unscored} {unscored === 1 ? "job isn't" : "jobs aren't"} scored yet, so{" "}
          {unscored === 1 ? "it isn't" : "they aren't"} in the deck.{" "}
          <Link to="/jobs?view=unscored" className="text-accent underline underline-offset-2">
            Score {unscored === 1 ? "it" : "them"}
          </Link>
        </p>
      )}
      {last?.action === "skip" && <SkipReason key={last.job.id} job={last.job} />}
      {!front ? (
        <DiscoverEmpty journey={journey.data} minScore={minScore} />
      ) : (
        <div className="grid gap-8 lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)]">
          <section aria-label="Job deck" className="relative z-10 flex flex-col items-center gap-5">
            <div className="relative h-[min(34rem,calc(100dvh-max(var(--dock-h,0px),5rem)-17.75rem-var(--banner-h,4.25rem)))] min-h-[20rem] w-full max-w-md">
              {next && <BackCard job={next} />}
              <SwipeCard
                key={front.id}
                job={front}
                detail={frontDetail.data}
                mapping={prefs.swipe}
                leaving={leaving}
                enabled
                allowMouse={prefs.deck.mouse_drag}
                onCommit={commit}
              />
            </div>
            <DeckControls
              mapping={prefs.swipe}
              directions={directionsInUse}
              showButtons={prefs.deck.buttons}
              onPick={commit}
            />
            {wide && (
              <p className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-caption text-muted">
                {directionsInUse.map((direction) => (
                  <span key={direction}>
                    <kbd className="glass-ctl rounded-md px-2 py-0.5 font-mono text-ink">
                      {ARROWS[direction]}
                    </kbd>{" "}
                    {ACTION_LABELS[prefs.swipe[direction]].toLowerCase()}
                  </span>
                ))}
                <span>
                  <kbd className="glass-ctl rounded-md px-2 py-0.5 font-mono text-ink">U</kbd> undo
                </span>
              </p>
            )}
            {waiting.length > 0 && (
              <p role="status" className="text-caption text-muted">
                {waiting.length} {waiting.length === 1 ? "document is" : "documents are"} waiting for a free
                slot.
              </p>
            )}
          </section>
          {wide && (
            <SidePanel front={front} detailText={frontDetail.data?.description} upNext={items.slice(1, 5)} />
          )}
        </div>
      )}
    </>
  );
}

function DeckControls({
  mapping,
  directions,
  showButtons,
  onPick,
}: {
  mapping: Record<Direction, SwipeAction>;
  directions: Direction[];
  showButtons: boolean;
  onPick: (direction: Direction) => void;
}) {
  const buttons = directions.map((direction) => {
    const action = mapping[direction];
    const primary = action === "generate_resume" || action === "generate_resume_and_cover_letter";
    return (
      <button
        key={direction}
        type="button"
        aria-label={`${ACTION_LABELS[action]} (${ARROWS[direction]})`}
        title={`${ACTION_LABELS[action]} (${ARROWS[direction]})`}
        onClick={() => onPick(direction)}
        className={
          primary
            ? "glow-yellow flex size-16 items-center justify-center rounded-full bg-brand text-on-brand"
            : "glass-ctl flex size-14 items-center justify-center rounded-full text-ink"
        }
      >
        {ICONS[action]}
      </button>
    );
  });
  // With the buttons switched off, the same actions stay reachable for keyboards and screen readers.
  return showButtons ? (
    <div className="flex items-center justify-center gap-4">{buttons}</div>
  ) : (
    <div className="sr-only">{buttons}</div>
  );
}

function SidePanel({
  front,
  detailText,
  upNext,
}: {
  front: JobSummary;
  detailText: string | undefined;
  upNext: JobSummary[];
}) {
  return (
    <aside
      aria-label="About this job"
      className="glass cut-tr grid min-w-0 grid-cols-[minmax(0,1fr)] content-start gap-5 rounded-card p-6"
    >
      <div>
        <h2 className="font-display text-caption tracking-wide text-muted uppercase">About the role</h2>
        <p className="glass-plate mt-2 line-clamp-[12] rounded-control p-3 text-secondary break-words whitespace-pre-line">
          {detailText ?? "Loading…"}
        </p>
        <Link
          to={`/jobs/${String(front.id)}`}
          state={{ from: "discover" }}
          className="mt-3 inline-block text-secondary text-accent underline underline-offset-2"
        >
          Open the full job page
        </Link>
        {fromAdzuna(front) && (
          <p className="mt-1 text-caption text-muted">
            via <AdzunaCredit className="underline underline-offset-2 hover:text-ink" />
          </p>
        )}
      </div>
      {upNext.length > 0 && (
        <div>
          <h2 className="font-display text-caption tracking-wide text-muted uppercase">Up next</h2>
          <ul className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-2">
            {upNext.map((job) => (
              <li
                key={job.id}
                className="glass-plate flex items-center justify-between gap-3 rounded-control px-3 py-2 text-secondary"
              >
                <span className="min-w-0 truncate">
                  {job.title} · {job.company}
                </span>
                <span className="font-mono">{job.match_score}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}
