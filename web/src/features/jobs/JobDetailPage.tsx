import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ArrowLeft, ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { Link, useLocation, useParams } from "react-router";

import type { ApplicationStatus, DocumentKind, JobDetail } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys } from "@/api/queries";
import { Button, Card, ErrorNote, Field, Meta, SegmentedControl, Select, Textarea } from "@/components/ui";
import { useToast } from "@/components/Toaster";
import { useBreakpoint } from "@/lib/breakpoints";
import { formatDate, formatSalary, STATUS_LABELS, STATUS_ORDER, yearsAskedLabel } from "@/lib/format";

import { useBackToDeck } from "@/features/discover/useBackToDeck";
import { JobSteps } from "@/features/journey/JobSteps";
import { BottomDock } from "@/features/shell/BottomDock";

import { DocumentPanel } from "./DocumentPanel";
import { FullDescriptionDialog } from "./FullDescriptionDialog";
import { FollowUp } from "./FollowUp";
import { AdzunaCredit, fromAdzuna } from "./AdzunaCredit";
import { MatchCard, useRescore } from "./MatchCard";
import { StatusText } from "./StatusText";
import { DOCUMENT_NAMES, useGenerateDocument } from "./useGenerateDocument";

type Job = JobDetail;

export function JobDetailPage() {
  const jobId = Number(useParams().jobId);
  const job = useQuery({
    queryKey: keys.job(jobId),
    queryFn: () => unwrap(client.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: jobId } } })),
    enabled: Number.isInteger(jobId) && jobId > 0,
  });

  if (job.isPending) return <JobSkeleton />;
  if (job.isError) return <ErrorNote {...describeError(job.error)} />;
  return <JobDetail job={job.data} />;
}

function JobSkeleton() {
  return (
    <div role="status" className="flex flex-col gap-4">
      <span className="sr-only">Loading job…</span>
      <div aria-hidden className="h-10 w-2/3 animate-pulse rounded-control bg-subtle" />
      <div aria-hidden className="h-48 animate-pulse rounded-card bg-subtle" />
      <div aria-hidden className="h-64 animate-pulse rounded-card bg-subtle" />
    </div>
  );
}

/** The one thing to do next on this job. Below `lg` it sits in a bar above the tab bar; from `lg` in the side column. */
function NextStep({ job, kind }: { job: Job; kind: DocumentKind }) {
  const wide = useBreakpoint("lg");
  const queryClient = useQueryClient();
  const { running, generate } = useGenerateDocument(job.id, kind);
  const markApplied = useMutation({
    mutationFn: () =>
      unwrap(
        client.PATCH("/api/v1/jobs/{job_id}/application", {
          params: { path: { job_id: job.id } },
          body: { status: "submitted" },
        }),
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.job(job.id) }),
        queryClient.invalidateQueries({ queryKey: keys.jobs }),
        queryClient.invalidateQueries({ queryKey: keys.applications }),
      ]);
    },
  });

  const rescore = useRescore(job.id);
  const { current, follow_up_overdue: overdue } = job.journey;
  let action: ReactNode = null;
  if (current === "score") {
    action = (
      <Button variant="primary" size="lg" className="w-full" busy={rescore.busy} onClick={rescore.run}>
        {job.match === null ? "Score this job" : "Re-score with your latest profile"}
      </Button>
    );
  } else if ((current === "write" || current === "applied") && !job.documents[kind]) {
    action = (
      <Button
        variant="primary"
        size="lg"
        className="w-full"
        busy={generate.isPending || running !== undefined}
        onClick={() => generate.mutate()}
      >
        Write my {DOCUMENT_NAMES[kind]}
      </Button>
    );
  } else if (current === "applied") {
    action = (
      <Button
        variant="primary"
        size="lg"
        className="w-full"
        busy={markApplied.isPending}
        onClick={() => markApplied.mutate()}
      >
        Mark as applied
      </Button>
    );
  } else if (current === "follow_up" || overdue) {
    action = <FollowUp jobId={job.id} current={job.journey.follow_up_at} overdue={overdue} />;
  }
  if (!action) return null;

  return wide ? (
    <Card className="p-5">{action}</Card>
  ) : (
    <BottomDock>
      <section aria-label="Next step" className="border-b border-line px-5 py-3">
        <div className="mx-auto max-w-3xl">{action}</div>
      </section>
    </BottomDock>
  );
}

function JobDetail({ job }: { job: Job }) {
  const [tab, setTab] = useState<DocumentKind>("resume");
  const [showDescription, setShowDescription] = useState(false);
  const [pasting, setPasting] = useState(false);
  const back = useBackToDeck();
  const fromDeck = (useLocation().state as { from?: string } | null)?.from === "discover";
  const salary = formatSalary(job.salary_min, job.salary_max);
  const facts = [
    job.company || "Unknown company",
    job.location,
    salary,
    job.posted_date && `Posted ${formatDate(job.posted_date)}`,
  ].filter(Boolean);

  return (
    <>
      <Link
        to={fromDeck ? "/discover" : "/jobs"}
        aria-label={fromDeck ? "Back to the deck" : undefined}
        className="mb-4 inline-flex min-h-11 items-center gap-1 text-secondary text-muted hover:text-ink"
      >
        <ArrowLeft className="size-4" aria-hidden />
        {fromDeck ? "Discover" : "Jobs"}
      </Link>
      <header className="mb-8 max-w-3xl">
        <h1 className="font-display text-title tracking-tight md:text-[2.5rem] md:leading-[1.1]">
          {job.title}
        </h1>
        <p className="mt-2 text-subheading text-muted">{facts.join(" · ")}</p>
        <p className="mt-3 flex flex-wrap items-center gap-3">
          <StatusText status={job.application_status} />
          {job.archived_at && <Meta>Archived</Meta>}
          {job.triage === "waitlisted" && <Meta tone="accent">On your waitlist</Meta>}
          {job.triage === "skipped" && <Meta>Skipped in Discover</Meta>}
          {(job.triage === "waitlisted" || job.triage === "skipped") && (
            <Button variant="ghost" size="sm" busy={back.isPending} onClick={() => back.mutate(job.id)}>
              Back to Discover
            </Button>
          )}
        </p>
        <JobSteps journey={job.journey} />
      </header>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-10">
        <div className="flex min-w-0 flex-col gap-8">
          <div data-tour="match">
            <MatchCard
              jobId={job.id}
              match={job.match ?? null}
              usesLatestProfile={job.match_uses_latest_profile}
              yearsAsked={yearsAskedLabel(job.years_asked_min, job.years_asked_max)}
            />
          </div>

          <section data-tour="document" className="flex flex-col gap-4">
            <SegmentedControl
              kind="tabs"
              label="Documents"
              value={tab}
              onChange={setTab}
              options={(["resume", "cover_letter"] as const).map((kind) => ({
                value: kind,
                tabId: `tab-${kind}`,
                panelId: `panel-${kind}`,
                label: (
                  <>
                    {kind === "resume" ? "Résumé" : "Cover letter"}
                    {job.documents[kind] && (
                      <span className="ml-1.5 text-caption text-faint">v{job.documents[kind].version}</span>
                    )}
                  </>
                ),
              }))}
            />
            <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
              <DocumentPanel
                key={tab}
                jobId={job.id}
                kind={tab}
                latest={job.documents[tab] ?? null}
                canGenerate={job.match !== null}
                externalAction
              />
            </div>
          </section>

          <Card className="p-6">
            <button
              type="button"
              aria-expanded={showDescription}
              onClick={() => setShowDescription((value) => !value)}
              className="flex min-h-11 w-full items-center justify-between text-left text-heading font-semibold"
            >
              Job description
              <span className="text-secondary font-normal text-accent">
                {showDescription ? "Hide" : "Show"}
              </span>
            </button>
            <div
              className={clsx(
                "mt-3 text-secondary leading-relaxed whitespace-pre-wrap text-muted",
                !showDescription && "line-clamp-4",
              )}
            >
              {job.description || "No description was provided."}
            </div>
            {job.description_is_snippet && (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-control bg-subtle p-4 text-secondary">
                <p className="text-muted">
                  Only a short preview of this posting is saved, and the full text could not be read from the
                  job board. Jobs are scored from the full description only: paste it to have this one scored.
                </p>
                <Button variant="secondary" size="sm" onClick={() => setPasting(true)}>
                  Paste the full description
                </Button>
              </div>
            )}
          </Card>
          <FullDescriptionDialog jobId={job.id} open={pasting} onClose={() => setPasting(false)} />
        </div>

        <aside className="flex flex-col gap-4 lg:sticky lg:top-24 lg:self-start">
          <NextStep job={job} kind={tab} />
          <ApplicationCard job={job} />
          <JobActions job={job} />
        </aside>
      </div>
    </>
  );
}

function ApplicationCard({ job }: { job: Job }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [note, setNote] = useState(job.application_note);

  const update = useMutation({
    mutationFn: (body: { status?: ApplicationStatus; note?: string }) =>
      unwrap(
        client.PATCH("/api/v1/jobs/{job_id}/application", { params: { path: { job_id: job.id } }, body }),
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.job(job.id) }),
        queryClient.invalidateQueries({ queryKey: keys.jobs }),
        queryClient.invalidateQueries({ queryKey: keys.applications }),
      ]);
    },
    onError: (error) => {
      const { message, reference } = describeError(error);
      toast({ tone: "error", title: "Couldn't update the application", description: message, reference });
    },
  });

  return (
    <Card className="flex flex-col gap-4 p-5">
      <h2 className="text-subheading font-semibold">Application</h2>
      <Field label="Status">
        {(id) => (
          <Select
            id={id}
            value={job.application_status}
            disabled={update.isPending}
            onChange={(event) => update.mutate({ status: event.target.value as ApplicationStatus })}
          >
            {STATUS_ORDER.map((status) => (
              <option key={status} value={status}>
                {STATUS_LABELS[status]}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field
        label="Notes"
        hint={job.application_updated_at ? `Updated ${formatDate(job.application_updated_at)}` : undefined}
      >
        {(id, hint) => (
          <Textarea
            id={id}
            aria-describedby={hint}
            rows={4}
            maxLength={2000}
            value={note}
            placeholder="Contacts, interview dates, follow-ups…"
            onChange={(event) => setNote(event.target.value)}
          />
        )}
      </Field>
      <Button
        size="sm"
        busy={update.isPending}
        disabled={note === job.application_note}
        onClick={() => update.mutate({ note })}
        className="self-end"
      >
        Save notes
      </Button>
    </Card>
  );
}

function JobActions({ job }: { job: Job }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const archive = useMutation({
    mutationFn: () => {
      const options = { params: { path: { job_id: job.id } } };
      return unwrap(
        job.archived_at
          ? client.DELETE("/api/v1/jobs/{job_id}/archive", options)
          : client.POST("/api/v1/jobs/{job_id}/archive", options),
      );
    },
    onSuccess: async (updated) => {
      queryClient.setQueryData(keys.job(job.id), updated);
      await queryClient.invalidateQueries({ queryKey: keys.jobs });
      await queryClient.invalidateQueries({ queryKey: keys.applications });
      toast({ tone: "success", title: updated.archived_at ? "Job archived" : "Job restored" });
    },
  });

  return (
    <Card className="flex flex-col gap-2 p-5">
      {job.url && (
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-11 items-center gap-2 text-secondary font-medium text-accent hover:underline"
        >
          <ExternalLink className="size-4" aria-hidden />
          View original posting
        </a>
      )}
      {fromAdzuna(job) && <AdzunaCredit />}
      <Button
        variant="ghost"
        size="sm"
        className="justify-start px-0"
        busy={archive.isPending}
        onClick={() => archive.mutate()}
      >
        {job.archived_at ? "Restore to job list" : "Archive (hide from list)"}
      </Button>
      <p className="text-caption text-faint">Added {formatDate(job.created_at)}</p>
    </Card>
  );
}
