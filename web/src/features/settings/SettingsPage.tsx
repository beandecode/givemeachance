import { Link } from "react-router";

import { client, unwrap } from "@/api/client";
import { useConfig, useOverview, useSession } from "@/api/queries";
import { Button, buttonClass, Card } from "@/components/ui";
import { useStartTask } from "@/features/jobs/useStartTask";
import { PageHeader } from "@/features/shell/AppShell";
import { useLatestTask } from "@/features/tasks/TaskProvider";
import { isTerminal } from "@/features/tasks/taskCopy";

import { DeckSettings } from "./DeckSettings";

const PROVIDER_NAMES: Record<string, string> = { gemini: "AI analysis", adzuna: "Job board searches" };

export function SettingsPage() {
  const overview = useOverview();
  const config = useConfig();
  const session = useSession();
  const rescoring = useLatestTask((task) => task.task_type === "re_evaluate" && !isTerminal(task));
  const rescore = useStartTask(() =>
    unwrap(client.POST("/api/v1/evaluations/rerun", { body: { scope: "all", limit: 100 } })),
  );

  return (
    <>
      <PageHeader title="Settings" />
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-10">
        <div className="flex flex-col gap-8">
          <Card className="p-6 sm:p-8">
            <h2 className="text-heading font-semibold">Discover deck</h2>
            <p className="mt-1 mb-6 text-secondary text-muted">
              What each swipe does, which jobs appear, and how the app looks. Changes are saved as you make
              them.
            </p>
            <DeckSettings />
          </Card>
          <Card className="p-6 sm:p-8">
            <h2 className="text-heading font-semibold">Job search</h2>
            <p className="mt-1 text-secondary text-muted">
              Keywords, location, job levels and how many jobs to fetch and score now live on the Jobs page,
              right next to the search button.
            </p>
            <Link to="/jobs" className={`${buttonClass("secondary")} mt-4`}>
              Open the Jobs page
            </Link>
          </Card>
        </div>

        <aside className="flex flex-col gap-4 lg:sticky lg:top-24 lg:self-start">
          <Card className="p-5">
            <h2 className="text-subheading font-semibold">Today's usage</h2>
            {overview.isSuccess && (
              <ul className="mt-3 flex flex-col gap-3">
                {overview.data.usage.map((item) => (
                  <li key={item.provider} className="text-secondary">
                    <div className="flex justify-between">
                      <span>{PROVIDER_NAMES[item.provider] ?? item.provider}</span>
                      <span className="text-muted tabular-nums">
                        {item.used} / {item.limit}
                      </span>
                    </div>
                    <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-subtle">
                      <div
                        className={item.percent_used >= 90 ? "h-full bg-bad" : "h-full bg-ink"}
                        style={{ width: `${String(Math.min(100, item.percent_used))}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-caption text-muted">Limits reset daily.</p>
          </Card>

          <Card className="p-5">
            <h2 className="text-subheading font-semibold">Re-score jobs</h2>
            <p className="mt-1 mb-4 text-secondary text-muted">
              After changing your profile, score your saved jobs again so matches reflect the latest version.
              This scores up to 100 jobs and can use a good part of today's AI limit.
            </p>
            <Button busy={rescore.isPending || rescoring !== undefined} onClick={() => rescore.mutate()}>
              {rescoring ? "Re-scoring…" : "Re-score all jobs"}
            </Button>
          </Card>

          <Card className="p-5 text-secondary">
            <h2 className="text-subheading font-semibold">Account</h2>
            <p className="mt-2 text-muted">Signed in as {session.data?.user?.username}</p>
            {config.data?.llm_provider === "mock" && (
              <p className="mt-2 text-muted">
                This server runs in sample-data mode: AI results and job listings are generated locally.
              </p>
            )}
          </Card>
        </aside>
      </div>
    </>
  );
}
