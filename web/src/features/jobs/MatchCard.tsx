import { clsx } from "clsx";
import type { Schemas } from "@/api/client";
import { client, unwrap } from "@/api/client";
import { Alert, Button, Card, Meta } from "@/components/ui";
import { useLatestTask } from "@/features/tasks/TaskProvider";
import { isTerminal } from "@/features/tasks/taskCopy";
import { recommendationLabel, scoreTone } from "@/lib/format";

import { Score } from "./Score";
import { useStartTask } from "./useStartTask";

type Match = Schemas["MatchReport"];

const BAR = { good: "bg-good", warn: "bg-warn", bad: "bg-bad", none: "bg-line-strong" } as const;

function humanize(key: string): string {
  const label = key.replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function ReasonList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="mb-2 text-subheading font-semibold">{title}</h3>
      <ul className="flex list-disc flex-col gap-1.5 pl-5 text-secondary marker:text-faint">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function useRescore(jobId: number) {
  const running = useLatestTask((task) => task.task_type === "re_evaluate" && !isTerminal(task));
  const start = useStartTask(() =>
    unwrap(client.POST("/api/v1/evaluations/rerun", { body: { scope: "all", job_ids: [jobId] } })),
  );
  return { busy: start.isPending || running !== undefined, run: () => start.mutate() };
}

/** Explainable match: overall score, per-dimension scores and the reasons behind them. */
export function MatchCard({
  jobId,
  match,
  usesLatestProfile,
  yearsAsked = "",
}: {
  jobId: number;
  match: Match | null;
  usesLatestProfile: boolean;
  /** "Asks for 5+ years": read from the posting, shown beside the score and never part of it. */
  yearsAsked?: string;
}) {
  const rescore = useRescore(jobId);

  if (!match) {
    return (
      <Card className="flex flex-col items-start gap-3 p-6">
        <h2 className="text-heading font-semibold">Match analysis</h2>
        <p className="text-secondary text-muted">This job hasn't been scored against your profile yet.</p>
        {yearsAsked && <Meta>{yearsAsked}</Meta>}
        <Button variant="primary" busy={rescore.busy} onClick={rescore.run}>
          Score this job
        </Button>
      </Card>
    );
  }

  const dimensions = Object.entries(match.dimension_scores);
  return (
    <Card className="hud cut-tr flex flex-col gap-6 p-6 md:p-8">
      <div className="flex items-center gap-5 md:gap-8">
        <Score score={match.total_score} variant="hero" />
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-title tracking-tight">
            {recommendationLabel(match.recommendation_level) || "Match analysis"}
          </h2>
          <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
            <Meta>{`${humanize(match.confidence)} confidence`}</Meta>
            {yearsAsked && <Meta>{yearsAsked}</Meta>}
          </p>
          {match.fit_reason && (
            <p className="mt-3 text-subheading leading-relaxed text-muted">{match.fit_reason}</p>
          )}
        </div>
      </div>

      {!usesLatestProfile && (
        <Alert tone="warn" title="Scored with an older version of your profile">
          <Button size="sm" className="mt-2" busy={rescore.busy} onClick={rescore.run}>
            Re-score with the latest profile
          </Button>
        </Alert>
      )}

      {dimensions.length > 0 && (
        <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
          {dimensions.map(([key, value]) => (
            <div key={key} className="grid grid-cols-[1fr_auto] gap-y-1.5 text-secondary">
              <dt>{humanize(key)}</dt>
              <dd className="font-medium tabular-nums">{value}</dd>
              <dd className="col-span-2 h-1 overflow-hidden rounded-full bg-subtle" aria-hidden>
                <div
                  className={clsx("h-full rounded-full", BAR[scoreTone(value)])}
                  style={{ width: `${String(value)}%` }}
                />
              </dd>
            </div>
          ))}
        </dl>
      )}

      <div className="grid gap-6 sm:grid-cols-2">
        <ReasonList
          title="Why it fits"
          items={[
            ...match.strengths,
            ...match.match_reasons.filter((reason) => !match.strengths.includes(reason)),
          ]}
        />
        <ReasonList title="Gaps" items={match.gaps} />
        <ReasonList title="Watch out for" items={match.risk_flags} />
        <ReasonList title="Unclear from your profile" items={match.missing_information} />
      </div>
    </Card>
  );
}
