import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ok, server } from "@/test/server";
import { renderRoute } from "@/test/render";

import { Tour } from "./Tour";
import { tourSeen, tourSteps } from "./tourSteps";

function open(live = true) {
  const onClose = vi.fn();
  const view = renderRoute([{ path: "*", element: <Tour live={live} onClose={onClose} /> }], "/discover");
  return { ...view, onClose, user: userEvent.setup() };
}

describe("Tour", () => {
  beforeEach(() => {
    window.localStorage.clear();
    server.use(
      http.get("*/api/v1/jobs", () =>
        ok({
          total: 2,
          items: [
            { id: 3, application_status: "draft" },
            { id: 7, application_status: "interview" },
          ],
        }),
      ),
    );
  });

  it("starts with an introduction and walks through the screens", async () => {
    const { user, router } = open();
    expect(await screen.findByRole("heading", { name: "Welcome to GivemeaChance" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Take the tour" }));
    expect(screen.getByRole("heading", { name: "Decide in seconds" })).toBeInTheDocument();
    expect(screen.getByText("1 of 9")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/discover");

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(router.state.location.pathname).toBe("/jobs");
    await user.click(screen.getByRole("button", { name: "Next" }));
    // The job page stops use a sample job that already has documents.
    expect(router.state.location.pathname).toBe("/jobs/7");
    expect(screen.getByRole("heading", { name: "Why it fits" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("heading", { name: "Every job, ranked" })).toBeInTheDocument();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("heading", { name: "Why it fits" })).toBeInTheDocument();
  });

  it("is remembered once skipped or finished", async () => {
    const { user, onClose } = open();
    await user.click(await screen.findByRole("button", { name: "Skip" }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(tourSeen()).toBe(true);
  });

  it("ends on the live demo button when there is one, else on a closing note", () => {
    expect(tourSteps(1, true).at(-1)).toMatchObject({ title: "Now try it for real" });
    expect(tourSteps(1, false).at(-1)).toMatchObject({ title: "That is the tour", target: null });
    expect(tourSteps(null, true)[2]).toMatchObject({ path: "/jobs" });
  });
});
