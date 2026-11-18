import { Search } from "lucide-react";
import { Link } from "react-router";

import { Button, buttonClass } from "@/components/ui";

import { useSearchStart } from "./useSearchStart";

/** Starts a job-board search with the saved preferences, or points to the profile when the search gate is closed. */
export function SearchButton() {
  const { state, running, start } = useSearchStart();

  if (state === "blocked") {
    return (
      <Link to="/onboarding" className={buttonClass("primary")}>
        Finish your profile to search
      </Link>
    );
  }
  const force = state === "force";
  return (
    <Button
      variant="primary"
      icon={<Search className="size-4" aria-hidden />}
      busy={start.isPending || running}
      disabled={state === "loading"}
      onClick={() => start.mutate({ force })}
      title={
        force ? "Your profile is missing some important details; results may be less accurate." : undefined
      }
    >
      {running ? "Searching…" : force ? "Search anyway" : "Search job board"}
    </Button>
  );
}
