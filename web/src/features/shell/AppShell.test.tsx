import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { ok, server } from "@/test/server";
import { renderRoute } from "@/test/render";

import { AppShell } from "./AppShell";

const routes = [
  { path: "/", element: <AppShell />, children: [{ path: "jobs", element: <p>Jobs screen</p> }] },
];

describe("AppShell demo mode", () => {
  it("shows a read-only banner and no sign-out in the demo", async () => {
    server.use(
      http.get("*/api/v1/config", () =>
        ok({
          registration_open: false,
          demo_mode: true,
          demo_live: false,
          guest: false,
          llm_provider: "mock",
          job_source: "mock",
          search_results_per_run: 10,
        }),
      ),
    );
    renderRoute(routes, "/jobs");

    expect(await screen.findByRole("status")).toHaveTextContent(/read-only demo/i);
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  });

  it("opens the tour on a first visit to the demo, and again from the banner", async () => {
    window.localStorage.clear();
    server.use(
      http.get("*/api/v1/config", () =>
        ok({
          registration_open: false,
          demo_mode: true,
          demo_live: false,
          guest: false,
          llm_provider: "mock",
          job_source: "mock",
          search_results_per_run: 10,
        }),
      ),
      http.get("*/api/v1/jobs", () => ok({ total: 0, items: [] })),
    );
    const user = userEvent.setup();
    renderRoute(wild, "/jobs");

    expect(await screen.findByRole("heading", { name: "Welcome to GivemeaChance" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Skip" }));
    expect(screen.queryByRole("heading", { name: "Welcome to GivemeaChance" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Take the tour" }));
    expect(screen.getByRole("heading", { name: "Welcome to GivemeaChance" })).toBeInTheDocument();
  });

  it("offers a guest workspace in the live demo and a way back from it", async () => {
    let guest = false;
    server.use(
      http.get("*/api/v1/config", () =>
        ok({
          registration_open: false,
          demo_mode: !guest,
          demo_live: true,
          guest,
          llm_provider: "gemini",
          job_source: "adzuna_api",
          search_results_per_run: 5,
        }),
      ),
      http.post("*/api/v1/demo/guest", () => {
        guest = true;
        return ok({ user: { id: 9, username: "guest_1", is_admin: false } }, 201);
      }),
      http.delete("*/api/v1/session", () => {
        guest = false;
        return ok({ user: null });
      }),
    );
    const user = userEvent.setup();
    renderRoute(wild, "/jobs");

    await user.click(await screen.findByRole("button", { name: "Try it live" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/deleted after 24 hours/i);
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back to the sample workspace" }));
    expect(await screen.findByRole("button", { name: "Try it live" })).toBeInTheDocument();
  });

  it("has no banner and keeps sign-out outside the demo", async () => {
    renderRoute(routes, "/jobs");

    expect(await screen.findByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(screen.queryByText(/read-only demo/i)).not.toBeInTheDocument();
  });
});

const wild = [{ path: "/", element: <AppShell />, children: [{ path: "*", element: <p>Screen</p> }] }];

function indicator(): HTMLElement {
  const node = document.querySelector<HTMLElement>("#bottom-dock nav > span[aria-hidden]");
  if (!node) throw new Error("tab indicator missing");
  return node;
}

describe("AppShell tab motion", () => {
  it.each([
    ["/discover", "translate-x-0"],
    ["/jobs", "translate-x-full"],
    ["/jobs/12", "translate-x-full"],
    ["/applications", "translate-x-[200%]"],
    ["/profile", "translate-x-[300%]"],
  ])("puts the tab indicator under the tab of %s", async (path, expected) => {
    renderRoute(wild, path);
    await screen.findByText("Screen");
    expect(indicator()).toHaveClass(expected);
    expect(indicator()).not.toHaveClass("opacity-0");
  });

  it.each(["/settings", "/onboarding"])("hides the tab indicator on %s, which has no tab", async (path) => {
    renderRoute(wild, path);
    await screen.findByText("Screen");
    expect(indicator()).toHaveClass("opacity-0");
  });

  it("lets a page rise in when the section changes, but not on first load", async () => {
    const { router } = renderRoute(wild, "/jobs");
    await screen.findByText("Screen");
    expect(document.querySelector(".route-enter")).toBeNull();

    await act(() => router.navigate("/profile"));
    expect(document.querySelector(".route-enter")).not.toBeNull();
    expect(indicator()).toHaveClass("translate-x-[300%]");
  });
});
