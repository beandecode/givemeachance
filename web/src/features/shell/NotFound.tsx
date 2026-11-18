import { Link } from "react-router";

import { EmptyState, buttonClass } from "@/components/ui";

export function NotFound() {
  return (
    <EmptyState title="Page not found">
      <p>That page doesn't exist or was moved.</p>
      <Link to="/jobs" className={`${buttonClass("secondary")} mt-4`}>
        Go to your jobs
      </Link>
    </EmptyState>
  );
}
