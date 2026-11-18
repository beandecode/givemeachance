import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { DEFAULT_PREFERENCES } from "@/features/discover/actions";
import { useGlassLevel } from "@/features/shell/useGlassLevel";
import { renderRoute } from "@/test/render";
import { ok, server } from "@/test/server";

import { assignAction, DeckSettings } from "./DeckSettings";

function serve() {
  const saved: unknown[] = [];
  server.use(
    http.get("*/api/v1/preferences", () => ok(saved.length ? saved[saved.length - 1] : DEFAULT_PREFERENCES)),
    http.put("*/api/v1/preferences", async ({ request }) => {
      const body = await request.json();
      saved.push(body);
      return ok(body);
    }),
    http.get("*/api/v1/jobs", () => ok({ items: [], total: 0, limit: 20, offset: 0 })),
  );
  return saved;
}

const render = () => renderRoute([{ path: "/settings", element: <DeckSettings /> }], "/settings");

describe("assignAction", () => {
  it("swaps with the direction that already had the action", () => {
    const next = assignAction(DEFAULT_PREFERENCES.swipe, "right", "skip");
    expect(next).toEqual({ left: "generate_resume", right: "skip", up: "waitlist", down: "details" });
  });

  it("lets several directions stay unused", () => {
    const next = assignAction(assignAction(DEFAULT_PREFERENCES.swipe, "up", "none"), "down", "none");
    expect(next).toMatchObject({ up: "none", down: "none", left: "skip", right: "generate_resume" });
  });
});

describe("DeckSettings", () => {
  it("shows the current mapping, threshold and toggles", async () => {
    serve();
    render();

    expect(await screen.findByLabelText(/Swipe right/)).toHaveValue("generate_resume");
    expect(screen.getByLabelText(/Swipe left/)).toHaveValue("skip");
    expect(screen.getByLabelText(/Swipe up/)).toHaveValue("waitlist");
    expect(screen.getByLabelText(/Swipe down/)).toHaveValue("details");
    expect(screen.getByLabelText(/Minimum match score: 70/)).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /Drag cards with the mouse/ })).toBeChecked();
    expect(screen.getByRole("switch", { name: /Show buttons under the card/ })).toBeChecked();
  });

  it("saves a remapped direction (swapping the other one) at once", async () => {
    const saved = serve();
    render();
    await userEvent.setup().selectOptions(await screen.findByLabelText(/Swipe right/), "skip");

    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0]).toMatchObject({
      swipe: { left: "generate_resume", right: "skip", up: "waitlist", down: "details" },
    });
    expect(screen.getByLabelText(/Swipe left/)).toHaveValue("generate_resume");
  });

  it("saves the threshold, the toggles and the glass level", async () => {
    const saved = serve();
    render();
    const user = userEvent.setup();

    fireEvent.change(await screen.findByLabelText(/Minimum match score/), { target: { value: "85" } });
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0]).toMatchObject({ deck: { min_score: 85, mouse_drag: true, buttons: true } });

    await user.click(screen.getByRole("switch", { name: /Drag cards with the mouse/ }));
    await waitFor(() => expect(saved).toHaveLength(2));
    expect(saved[1]).toMatchObject({ deck: { min_score: 85, mouse_drag: false } });

    await user.selectOptions(screen.getByLabelText("Glass effect"), "strong");
    await waitFor(() => expect(saved).toHaveLength(3));
    expect(saved[2]).toMatchObject({ ui: { glass: "strong" } });
    expect(screen.getByText(/Strong blurs the most/)).toBeInTheDocument();
  });

  it("resets everything to the defaults", async () => {
    const saved = serve();
    render();
    await userEvent.setup().selectOptions(await screen.findByLabelText(/Swipe up/), "none");
    await waitFor(() => expect(saved).toHaveLength(1));

    await userEvent.setup().click(screen.getByRole("button", { name: "Reset to defaults" }));
    await waitFor(() => expect(saved).toHaveLength(2));
    expect(saved[1]).toEqual(DEFAULT_PREFERENCES);
  });
});

describe("useGlassLevel", () => {
  function Probe() {
    useGlassLevel();
    return null;
  }

  it("puts the saved level on <html> and leaves it off for automatic", async () => {
    server.use(
      http.get("*/api/v1/preferences", () => ok({ ...DEFAULT_PREFERENCES, ui: { glass: "medium_plus" } })),
    );
    renderRoute([{ path: "/", element: <Probe /> }], "/");
    await waitFor(() => expect(document.documentElement.dataset.gi).toBe("medium_plus"));
  });

  it("uses no override for automatic", async () => {
    document.documentElement.dataset.gi = "strong";
    server.use(http.get("*/api/v1/preferences", () => ok(DEFAULT_PREFERENCES)));
    renderRoute([{ path: "/", element: <Probe /> }], "/");
    await waitFor(() => expect(document.documentElement.dataset.gi).toBeUndefined());
  });
});
