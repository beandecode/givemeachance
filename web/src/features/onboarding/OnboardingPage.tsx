import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect } from "react";
import { Link, useSearchParams } from "react-router";

import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys, useJourney, useProfile } from "@/api/queries";
import { Alert, buttonClass, Card, ErrorNote } from "@/components/ui";
import { SearchButton } from "@/features/jobs/SearchButton";
import { MissingInfoForm } from "@/features/profile/MissingInfoForm";
import type { MasterProfile } from "@/features/profile/profileModel";
import { readProfile } from "@/features/profile/profileModel";
import { ProfileView } from "@/features/profile/ProfileView";
import { ApproveButton } from "@/features/profile/ReviewActions";
import { SearchPreferencesForm } from "@/features/settings/SearchPreferencesForm";
import { useLatestTask } from "@/features/tasks/TaskProvider";
import { isTerminal } from "@/features/tasks/taskCopy";

import { BackgroundForm } from "./BackgroundForm";

type Step = "background" | "review" | "preferences" | "find" | "pick" | "write" | "done";

const STEPS: { id: Exclude<Step, "done">; label: string }[] = [
  { id: "background", label: "Your background" },
  { id: "review", label: "Check your profile" },
  { id: "preferences", label: "What to search for" },
  { id: "find", label: "Find jobs" },
  { id: "pick", label: "Pick jobs" },
  { id: "write", label: "Write your first résumé" },
];

function Stepper({ current }: { current: Step }) {
  const index = current === "done" ? STEPS.length : STEPS.findIndex((step) => step.id === current);
  const shown = Math.min(index + 1, STEPS.length);
  return (
    <div className="mb-8" role="group" aria-label="Setup progress">
      <p className="text-secondary text-muted">
        {current === "done"
          ? "Setup complete"
          : `Step ${String(shown)} of ${String(STEPS.length)}: ${STEPS[index]?.label ?? ""}`}
      </p>
      <div aria-hidden className="mt-3 h-0.5 overflow-hidden rounded-full bg-subtle">
        <div
          className="h-full rounded-full bg-ink transition-[width] duration-(--duration-slow) ease-(--ease-calm)"
          style={{
            width: `${String(Math.round((Math.min(index + 1, STEPS.length) / STEPS.length) * 100))}%`,
          }}
        />
      </div>
    </div>
  );
}

/** First-run setup, derived from saved state so it can be left and resumed at any point. */
export function OnboardingPage() {
  const profile = useProfile();
  const preferences = useQuery({
    queryKey: keys.searchPreferences,
    queryFn: () => unwrap(client.GET("/api/v1/search-preferences")),
  });
  const suggested = useQuery({
    queryKey: keys.suggestedPreferences,
    queryFn: () => unwrap(client.GET("/api/v1/search-preferences/suggested")),
    enabled: preferences.data?.source === "default",
  });
  const [params, setParams] = useSearchParams();
  const journey = useJourney();
  const building = useLatestTask((task) => task.task_type === "synthesize_profile" && !isTerminal(task));

  const current = profile.data?.profile;
  const later = (key: string) => journey.data?.steps.find((item) => item.key === key)?.status === "done";
  const step: Step | null =
    profile.isSuccess && preferences.isSuccess && journey.isSuccess
      ? !current?.master_profile || params.get("step") === "background" || building
        ? "background"
        : current.review_status !== "approved"
          ? "review"
          : preferences.data.source !== "user"
            ? "preferences"
            : !later("find_jobs")
              ? "find"
              : !later("pick")
                ? "pick"
                : !later("write")
                  ? "write"
                  : "done"
      : null;

  useEffect(() => {
    if (step) window.scrollTo({ top: 0 });
  }, [step]);

  if (profile.isPending || preferences.isPending) return <OnboardingSkeleton />;
  if (profile.isError) return <ErrorNote {...describeError(profile.error)} />;
  if (preferences.isError) return <ErrorNote {...describeError(preferences.error)} />;
  if (!step) return null;

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="font-display text-title tracking-wide uppercase md:text-[2.25rem]">
        Set up your job search
      </h1>
      <p className="mt-2 mb-8 text-secondary text-muted">
        Six short steps, from your résumé to your first tailored document. Your profile is the single source
        for every match and document.
      </p>
      <Stepper current={step} />

      {step === "background" && (
        <Card className="p-6 sm:p-8">
          <h2 className="mb-1 text-heading font-semibold">Tell us about your experience</h2>
          <p className="mb-6 text-secondary text-muted">
            We turn your résumé into a structured profile. Nothing is invented. Gaps become questions for you.
          </p>
          <BackgroundForm onStarted={() => setParams({}, { replace: true })} />
        </Card>
      )}

      {step === "review" && current?.master_profile && (
        <ReviewStep profileId={current.id} master={current.master_profile} />
      )}

      {step === "preferences" &&
        (suggested.isPending && preferences.data.source === "default" ? (
          <OnboardingSkeleton />
        ) : (
          <Card className="p-6 sm:p-8">
            <h2 className="mb-1 text-heading font-semibold">What should we search for?</h2>
            <p className="mb-6 text-secondary text-muted">
              Prefilled from your profile. You can change it any time from Search options on the Jobs page.
            </p>
            <SearchPreferencesForm
              initial={(suggested.data ?? preferences.data).config}
              submitLabel="Save and continue"
            />
          </Card>
        ))}

      {step === "find" && (
        <GuideCard
          title="Find your first jobs"
          text={
            journey.data?.counts.jobs
              ? "Your jobs are saved but not scored yet. Score them to see how well each one fits."
              : "Search the job board. New jobs are scored against your profile, so the good ones come first."
          }
        >
          {journey.data?.counts.jobs ? (
            <Link to="/jobs?view=unscored" className={buttonClass("primary")}>
              Score my jobs
            </Link>
          ) : (
            <SearchButton />
          )}
        </GuideCard>
      )}

      {step === "pick" && (
        <GuideCard
          title="Pick the jobs you like"
          text="Open Discover and swipe: right writes your résumé for that job, left skips it, up saves it for later, down opens the details. Arrow keys work too."
        >
          <Link to="/discover" className={buttonClass("primary")}>
            Open Discover
          </Link>
        </GuideCard>
      )}

      {step === "write" && (
        <GuideCard
          title="Write and check your first résumé"
          text="Open a job you picked, write the résumé, and read the checks before you send it. Edit anything that does not sound like you."
        >
          <Link
            to={journey.data?.steps.find((item) => item.key === "write")?.cta_route || "/discover"}
            className={buttonClass("primary")}
          >
            Write my résumé
          </Link>
        </GuideCard>
      )}

      {step === "done" && (
        <Card className="flex flex-col items-center gap-5 p-8 text-center">
          <span className="flex size-14 items-center justify-center rounded-full bg-good-soft text-good">
            <Check className="size-6" aria-hidden />
          </span>
          <div>
            <h2 className="font-display text-title tracking-tight">You're all set</h2>
            <p className="mt-2 text-secondary text-muted">
              When you send an application, mark the job as applied so you can follow it up.
            </p>
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            <Link to="/discover" className={buttonClass("primary")}>
              Go to Discover
            </Link>
            <Link to="/applications" className={buttonClass("secondary")}>
              Applications
            </Link>
          </div>
        </Card>
      )}
    </div>
  );
}

function GuideCard({ title, text, children }: { title: string; text: string; children: ReactNode }) {
  return (
    <Card className="flex flex-col items-start gap-4 p-6 sm:p-8">
      <div>
        <h2 className="text-heading font-semibold">{title}</h2>
        <p className="mt-1 text-secondary text-muted">{text}</p>
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </Card>
  );
}

function ReviewStep({ profileId, master }: { profileId: number; master: MasterProfile }) {
  const view = readProfile(master);
  const high = view.missing.filter((item) => item.priority === "high");
  return (
    <div className="flex flex-col gap-4">
      <Alert tone="accent" title="Is this you?">
        Check the details below. Edit anything that's wrong, then approve. Only approved profiles are used.
      </Alert>
      {high.length > 0 && (
        <Card className="p-5">
          <h2 className="text-subheading font-semibold">A few important details are missing</h2>
          <p className="mt-1 mb-4 text-secondary text-muted">Answer these to unlock job search.</p>
          <MissingInfoForm profileId={profileId} items={high} />
        </Card>
      )}
      <ProfileView profile={view} />
      <div className="sticky bottom-[calc(var(--dock-h,5rem)+0.5rem)] z-10 flex flex-wrap justify-end gap-2 glass glass-plate rounded-card p-3 shadow-pop lg:bottom-4">
        <Link to="/profile?edit=1" className={buttonClass("secondary")}>
          Edit details
        </Link>
        <ApproveButton profileId={profileId} />
      </div>
    </div>
  );
}

function OnboardingSkeleton() {
  return (
    <div role="status" className="mx-auto flex max-w-3xl flex-col gap-4">
      <span className="sr-only">Loading…</span>
      <div aria-hidden className="h-10 w-2/3 animate-pulse rounded-control bg-subtle" />
      <div aria-hidden className="h-64 animate-pulse rounded-card bg-subtle" />
    </div>
  );
}
