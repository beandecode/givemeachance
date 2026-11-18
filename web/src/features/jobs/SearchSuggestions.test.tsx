import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { renderRoute } from "@/test/render";
import { ok, server } from "@/test/server";

import { applySuggestion, SearchSuggestions } from "./SearchSuggestions";

const config = {
  adzuna: {} as never,
  target_levels: ["mid", "senior"] as ("mid" | "senior")[],
  work_modes: [],
  exclude_title_words: ["sales"],
  knockouts: [],
};

describe("applySuggestion", () => {
  it("removes a level or adds a title word without touching the rest", () => {
    expect(
      applySuggestion(config, { kind: "remove_level", value: "senior", count: 3 }).target_levels,
    ).toEqual(["mid"]);
    expect(
      applySuggestion(config, { kind: "exclude_word", value: "marketing", count: 3 }).exclude_title_words,
    ).toEqual(["sales", "marketing"]);
  });
});

describe("SearchSuggestions", () => {
  it("offers a suggestion and saves the changed settings only when applied", async () => {
    const saved: unknown[] = [];
    server.use(
      http.get("*/api/v1/search-suggestions", () =>
        ok([{ kind: "remove_level", value: "senior", count: 3 }]),
      ),
      http.put("*/api/v1/search-preferences", async ({ request }) => {
        saved.push(await request.json());
        return ok({ source: "user", config });
      }),
    );
    renderRoute([{ path: "/", element: <SearchSuggestions config={config} /> }], "/");

    expect(await screen.findByText(/You skipped 3 jobs as too senior/)).toBeInTheDocument();
    expect(saved).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(saved).toHaveLength(1);
    expect((saved[0] as { target_levels: string[] }).target_levels).toEqual(["mid"]);
  });

  it("renders nothing without suggestions", async () => {
    const { container } = renderRoute([{ path: "/", element: <SearchSuggestions config={config} /> }], "/");
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(container.querySelector("section")).toBeNull();
  });
});
