import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys, useConfig, useProfile } from "@/api/queries";
import { Alert, Button, buttonClass, Card, Dot, EmptyState, ErrorNote } from "@/components/ui";
import { PageHeader } from "@/features/shell/AppShell";
import { formatDate } from "@/lib/format";

import { MissingInfoForm } from "./MissingInfoForm";
import { ProfileEditor } from "./ProfileEditor";
import { readProfile } from "./profileModel";
import { ProfileView } from "./ProfileView";
import { ApproveButton, useReviewProfile } from "./ReviewActions";

export function reviewStatus(status: string) {
  if (status === "approved") return <Dot tone="good">Approved</Dot>;
  if (status === "needs_changes") return <Dot tone="warn">Needs changes</Dot>;
  return <Dot tone="accent">Waiting for review</Dot>;
}

export function ProfilePage() {
  const snapshot = useProfile();
  const [params, setParams] = useSearchParams();
  const editing = params.get("edit") === "1";
  const setEditing = (value: boolean) => setParams(value ? { edit: "1" } : {}, { replace: true });
  const review = useReviewProfile();
  const [showHistory, setShowHistory] = useState(false);
  const config = useConfig();
  // Demo visitors (the read-only sample and live guests) cannot edit a profile by hand: no personal data (ADR-018).
  const demo = config.data?.demo_mode === true || config.data?.guest === true;
  const readOnlyDemo = config.data?.demo_mode === true;

  if (snapshot.isPending) return <ProfileSkeleton />;
  if (snapshot.isError) return <ErrorNote {...describeError(snapshot.error)} />;

  const { profile, readiness } = snapshot.data;
  if (!profile?.master_profile) {
    return (
      <>
        <PageHeader title="Profile" />
        <EmptyState title="No profile yet">
          <p>Your profile is built from your résumé. Everything else in the app starts from it.</p>
          <Link to="/onboarding" className={`${buttonClass("primary")} mt-4`}>
            Build my profile
          </Link>
        </EmptyState>
      </>
    );
  }

  const master = profile.master_profile;
  const view = readProfile(master);
  const completeness = Math.round(readiness.completeness_score);

  return (
    <>
      <PageHeader
        title="Profile"
        description={`Version ${String(profile.profile_version)} · ${
          profile.model_name === "user_edit" ? "edited by you" : "built from your résumé"
        } · ${formatDate(profile.created_at)}`}
        actions={
          !editing && (
            <>
              <Link to="/onboarding?step=background" className={buttonClass("secondary")}>
                Rebuild from résumé
              </Link>
              {!demo && (
                <Button variant="primary" onClick={() => setEditing(true)}>
                  Edit
                </Button>
              )}
            </>
          )
        }
      />

      {editing ? (
        <ProfileEditor
          original={master}
          onSaved={() => setEditing(false)}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-10">
          <div data-tour="profile" className="flex flex-col gap-4">
            {profile.review_status !== "approved" && (
              <Alert tone="accent" title="Check this version before using it">
                <p>Jobs are scored and documents are written from your approved profile.</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <ApproveButton profileId={profile.id} />
                  {profile.review_status !== "needs_changes" && (
                    <Button
                      busy={review.isPending}
                      onClick={() => review.mutate({ profileId: profile.id, status: "needs_changes" })}
                    >
                      Needs changes
                    </Button>
                  )}
                </div>
              </Alert>
            )}
            <ProfileView profile={view} />
          </div>
          <aside className="flex flex-col gap-4 lg:sticky lg:top-24 lg:self-start">
            <Card className="p-5">
              <div className="flex items-center justify-between">
                <h2 className="text-subheading font-semibold">Status</h2>
                {reviewStatus(profile.review_status)}
              </div>
              <p className="mt-4 text-secondary text-muted">Completeness</p>
              <div className="mt-1 flex items-center gap-3">
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-subtle">
                  <div className="h-full rounded-full bg-ink" style={{ width: `${String(completeness)}%` }} />
                </div>
                <span className="text-secondary font-medium">{completeness}%</span>
              </div>
              {readiness.allowed ? (
                <p className="mt-3 text-secondary text-good">Ready for job search.</p>
              ) : (
                <ul className="mt-3 list-disc space-y-1 pl-5 text-secondary text-muted">
                  {readiness.blocking_reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              )}
            </Card>
            {view.missing.length > 0 && (
              <Card className="p-5" data-tour="gaps">
                <h2 className="text-subheading font-semibold">Fill the gaps</h2>
                <p className="mt-1 mb-4 text-secondary text-muted">
                  Questions about what would make you stronger, such as a result without a number. An answer
                  lands on the job or project it is about, in a new version you review before it's used.
                </p>
                {readOnlyDemo ? (
                  <ul className="list-disc space-y-2 pl-5 text-secondary">
                    {view.missing.map((item) => (
                      <li key={item.field}>{item.question}</li>
                    ))}
                  </ul>
                ) : (
                  <MissingInfoForm profileId={profile.id} items={view.missing} />
                )}
                {readOnlyDemo && (
                  <p className="mt-3 text-caption text-muted">
                    Answering is off in this read-only workspace; it works in Try it live.
                  </p>
                )}
              </Card>
            )}
            <Card className="p-5">
              <button
                type="button"
                className="flex min-h-11 w-full items-center justify-between text-subheading font-semibold"
                aria-expanded={showHistory}
                onClick={() => setShowHistory((value) => !value)}
              >
                Version history
                <span className="text-secondary font-normal text-accent">
                  {showHistory ? "Hide" : "Show"}
                </span>
              </button>
              {showHistory && <VersionHistory />}
            </Card>
          </aside>
        </div>
      )}
    </>
  );
}

function VersionHistory() {
  const versions = useQuery({
    queryKey: keys.profileVersions,
    queryFn: () => unwrap(client.GET("/api/v1/profile/versions")),
  });
  if (versions.isPending)
    return <div aria-hidden className="mt-3 h-16 animate-pulse rounded-control bg-subtle" />;
  if (versions.isError) return <ErrorNote {...describeError(versions.error)} />;
  return (
    <ol className="mt-3 space-y-3 text-secondary">
      {versions.data.map((version) => (
        <li key={version.id} className="flex items-center justify-between gap-2">
          <span>
            v{version.profile_version}
            <span className="text-muted">
              {" "}
              · {version.model_name === "user_edit" ? "your edit" : "from résumé"} ·{" "}
              {formatDate(version.created_at)}
            </span>
          </span>
          {reviewStatus(version.review_status)}
        </li>
      ))}
    </ol>
  );
}

function ProfileSkeleton() {
  return (
    <div role="status" className="flex flex-col gap-4">
      <span className="sr-only">Loading your profile…</span>
      <div aria-hidden className="h-10 w-1/3 animate-pulse rounded-control bg-subtle" />
      <div aria-hidden className="h-96 animate-pulse rounded-card bg-subtle" />
    </div>
  );
}
