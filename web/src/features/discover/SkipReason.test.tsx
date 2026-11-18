import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import type { JobSummary } from "@/api/client";
import { renderRoute } from "@/test/render";
import { ok, server } from "@/test/server";

import { SkipReason } from "./SkipReason";

const job = { id: 7, title: "Staff Engineer" } as JobSummary;

describe("SkipReason", () => {
  it("records the chosen reason as a skip and then thanks the user", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.put("*/api/v1/jobs/:id/triage", async ({ request }) => {
        bodies.push(await request.json());
        return ok({ job_id: 7, action: "skipped", generate: null, tasks: [], queued_for_later: false });
      }),
    );
    renderRoute([{ path: "/", element: <SkipReason job={job} /> }], "/");

    expect(screen.getByText("Why skip Staff Engineer? Optional:")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Too senior" }));

    expect(await screen.findByText("Thanks, noted.")).toBeInTheDocument();
    expect(bodies).toEqual([{ action: "skipped", reason: "too_senior" }]);
    expect(screen.queryByRole("button", { name: "Pay" })).not.toBeInTheDocument();
  });
});
