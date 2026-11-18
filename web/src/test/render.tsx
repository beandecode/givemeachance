import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";

import { ToastProvider } from "@/components/Toaster";
import { TaskProvider } from "@/features/tasks/TaskProvider";
import { createQueryClient } from "@/queryClient";

/** Render a screen inside the app's providers at `path` (routes are relative to the /app basename). */
export function renderRoute(routes: { path: string; element: ReactNode }[], path: string) {
  const queryClient = createQueryClient();
  const router = createMemoryRouter(
    routes.map((route) => ({ ...route, element: <TaskProvider>{route.element}</TaskProvider> })),
    { initialEntries: [path] },
  );
  const view = render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...view, router, queryClient };
}
