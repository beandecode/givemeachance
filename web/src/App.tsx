import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter, Navigate } from "react-router";
import { RouterProvider } from "react-router/dom";

import { useJourney } from "@/api/queries";
import { ToastProvider } from "@/components/Toaster";
import { Spinner } from "@/components/ui";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { JobsPage } from "@/features/jobs/JobsPage";
import { AppShell } from "@/features/shell/AppShell";
import { NotFound } from "@/features/shell/NotFound";
import { TaskProvider } from "@/features/tasks/TaskProvider";

import { createQueryClient } from "./queryClient";

/** Users whose profile or search settings are not ready start with onboarding; everyone else lands on Discover. */
function Home() {
  const journey = useJourney();
  if (journey.isPending) return <Spinner />;
  const setUp = journey.data?.steps.every(
    (step) => (step.key !== "profile" && step.key !== "search_prefs") || step.status === "done",
  );
  return <Navigate to={setUp === false ? "/onboarding" : "/discover"} replace />;
}

const routes = [
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <TaskProvider>
          <AppShell />
        </TaskProvider>
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Home /> },
      {
        path: "discover",
        lazy: async () => ({ Component: (await import("@/features/discover/DiscoverPage")).DiscoverPage }),
      },
      { path: "jobs", element: <JobsPage /> },
      // Less-visited pages load on first use (react-markdown, dnd-kit stay out of the first download).
      {
        path: "jobs/:jobId",
        lazy: async () => ({ Component: (await import("@/features/jobs/JobDetailPage")).JobDetailPage }),
      },
      {
        path: "applications",
        lazy: async () => ({
          Component: (await import("@/features/applications/ApplicationsPage")).ApplicationsPage,
        }),
      },
      {
        path: "profile",
        lazy: async () => ({ Component: (await import("@/features/profile/ProfilePage")).ProfilePage }),
      },
      {
        path: "settings",
        lazy: async () => ({ Component: (await import("@/features/settings/SettingsPage")).SettingsPage }),
      },
      {
        path: "onboarding",
        lazy: async () => ({
          Component: (await import("@/features/onboarding/OnboardingPage")).OnboardingPage,
        }),
      },
      { path: "*", element: <NotFound /> },
    ],
  },
];

const router = createBrowserRouter(routes, { basename: "/app" });

export function App() {
  const [queryClient] = useState(createQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  );
}
