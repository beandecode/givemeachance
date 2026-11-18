import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { renderRoute } from "@/test/render";
import { journey, ok, server } from "@/test/server";

import { JourneyBar } from "./JourneyBar";

const routes = [{ path: "/jobs", element: <JourneyBar /> }];

function midSetup(overrides: Record<string, unknown> = {}) {
  const base = journey();
  const steps = base.steps.map((step) =>
    step.key === "pick" || step.key === "write" || step.key === "apply"
      ? {
          ...step,
          status: step.key === "pick" ? "current" : "todo",
          reason_code: "nothing_accepted",
          cta_label: "Pick jobs",
          cta_route: "/discover",
        }
      : step,
  );
  return journey({ completed: false, current: "pick", steps, ...overrides });
}

describe("JourneyBar", () => {
  it("shows the current step with its next action", async () => {
    server.use(http.get("*/api/v1/journey", () => ok(midSetup())));
    renderRoute(routes, "/jobs");

    expect(await screen.findByText(/Step 4 of 6: Pick jobs/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Pick jobs" })).toHaveAttribute("href", "/discover");
  });

  it("stays hidden once everything is done or the user hid it", async () => {
    server.use(http.get("*/api/v1/journey", () => ok(midSetup({ skipped: true }))));
    renderRoute(routes, "/jobs");

    await screen.findByRole("main", {}, { timeout: 200 }).catch(() => undefined);
    expect(screen.queryByRole("region", { name: "Setup guide" })).not.toBeInTheDocument();
  });

  it("hides itself when the cross is pressed", async () => {
    let skipped = false;
    server.use(
      http.get("*/api/v1/journey", () => ok(midSetup({ skipped }))),
      http.put("*/api/v1/journey", () => {
        skipped = true;
        return ok(midSetup({ skipped }));
      }),
    );
    renderRoute(routes, "/jobs");

    await userEvent.click(await screen.findByRole("button", { name: "Hide the setup guide" }));
    await expect(screen.findByRole("region", { name: "Setup guide" }, { timeout: 300 })).rejects.toThrow();
  });
});
