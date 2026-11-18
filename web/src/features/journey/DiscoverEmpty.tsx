import { Link } from "react-router";

import { buttonClass, EmptyState } from "@/components/ui";
import { SearchButton } from "@/features/jobs/SearchButton";

import type { Journey } from "./journeyCopy";

/** The empty Discover deck says why it is empty and offers the matching next action. */
export function DiscoverEmpty({ journey, minScore }: { journey: Journey | undefined; minScore: number }) {
  const state = journey?.discover;
  const waiting = journey?.counts.pending ?? 0;
  const allJobs = (
    <Link to="/jobs" className={buttonClass("secondary")}>
      All jobs
    </Link>
  );

  if (state === "no_jobs") {
    return (
      <EmptyState title="No jobs yet">
        <p>Search the job board and new jobs are scored against your profile. The good ones appear here.</p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <SearchButton />
        </div>
      </EmptyState>
    );
  }
  if (state === "none_scored") {
    return (
      <EmptyState title="Your jobs are not scored yet">
        <p>Only scored jobs can be in the deck.</p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <Link to="/jobs?view=unscored" className={buttonClass("primary")}>
            Score them
          </Link>
          {allJobs}
        </div>
      </EmptyState>
    );
  }
  if (state === "below_threshold") {
    return (
      <EmptyState title={`Nothing at ${String(minScore)} or above`}>
        <p>
          {waiting} scored {waiting === 1 ? "job is" : "jobs are"} waiting below your score threshold. Lower
          the threshold in Settings, or search for more.
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <Link to="/settings" className={buttonClass("secondary")}>
            Lower the threshold
          </Link>
          <SearchButton />
        </div>
      </EmptyState>
    );
  }
  if (state === "all_decided") {
    return (
      <EmptyState title="You have decided on every job">
        <p>Search the job board for more, or look through all of your jobs.</p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <SearchButton />
          {allJobs}
        </div>
      </EmptyState>
    );
  }
  return (
    <EmptyState title="Nothing in the deck right now">
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        <SearchButton />
        {allJobs}
      </div>
    </EmptyState>
  );
}
