import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { apiError, ok, server } from "@/test/server";
import { renderRoute } from "@/test/render";

import { LoginPage } from "./LoginPage";

const routes = [
  { path: "/login", element: <LoginPage /> },
  { path: "/", element: <p>Home screen</p> },
  { path: "/jobs", element: <p>Jobs screen</p> },
];

describe("LoginPage", () => {
  it("explains a lockout without exposing internals", async () => {
    server.use(
      http.get("*/api/v1/session", () => ok({ user: null })),
      http.post("*/api/v1/session", () => apiError(429, 1005, "too many failed sign-in attempts")),
    );
    renderRoute(routes, "/login");

    await userEvent.type(await screen.findByLabelText("Username"), "alex");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many failed sign-in attempts");
  });

  it("returns to the requested page after signing in, but never off-site", async () => {
    server.use(
      http.get("*/api/v1/session", () => ok({ user: null })),
      http.post("*/api/v1/session", () => ok({ user: { id: 1, username: "alex", is_admin: false } })),
    );
    const { router } = renderRoute(routes, "/login?next=" + encodeURIComponent("//evil.example/jobs"));

    await userEvent.type(await screen.findByLabelText("Username"), "alex");
    await userEvent.type(screen.getByLabelText("Password"), "correct-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Home screen")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
  });
});

describe("LoginPage sign-up", () => {
  it("offers sign-up only while registration is open and creates the account", async () => {
    let created: unknown = null;
    server.use(
      http.get("*/api/v1/session", () => ok({ user: null })),
      http.get("*/api/v1/config", () =>
        ok({
          registration_open: true,
          demo_mode: false,
          demo_live: false,
          guest: false,
          llm_provider: "mock",
          job_source: "mock",
          search_results_per_run: 10,
        }),
      ),
      http.post("*/api/v1/account", async ({ request }) => {
        created = await request.json();
        return ok({ user: { id: 2, username: "newbie", is_admin: false } }, 201);
      }),
    );
    renderRoute(routes, "/login");

    await userEvent.click(await screen.findByRole("button", { name: "Create an account" }));
    expect(screen.getByRole("heading", { name: "Create your account" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Username"), "newbie");
    await userEvent.type(screen.getByLabelText("Password"), "a-long-password");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Home screen")).toBeInTheDocument();
    expect(created).toEqual({ username: "newbie", password: "a-long-password" });
  });
});
