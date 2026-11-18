import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useSession } from "@/api/queries";
import { Spinner } from "@/components/ui";

export function RequireAuth({ children }: { children: ReactNode }) {
  const session = useSession();
  const location = useLocation();
  if (session.isPending) return <Spinner label="Loading your workspace" />;
  if (!session.data?.user) {
    const next = location.pathname + location.search;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return children;
}
