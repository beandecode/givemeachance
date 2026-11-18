import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { ok, server } from "@/test/server";
import { renderRoute } from "@/test/render";

import { SearchPreferencesForm } from "./SearchPreferencesForm";

const adzuna = {
  country: "ca",
  keywords: ["backend engineer"],
  location: "Toronto",
  results_per_page: 10,
  max_pages: 1,
  days_old: 14,
  sort_by: "date" as const,
  salary_min: null,
  salary_max: null,
  distance: null,
  company: null,
  category: null,
  full_time: null,
  part_time: null,
  permanent: null,
  contract: null,
  what_and: null,
  what_or: null,
  what_phrase: null,
  what_exclude: null,
};

function renderForm(levels: ("junior" | "mid" | "senior" | "staff_plus" | "management")[]) {
  renderRoute(
    [
      {
        path: "/",
        element: (
          <SearchPreferencesForm
            initial={{
              adzuna,
              target_levels: levels,
              work_modes: [],
              exclude_title_words: [],
              knockouts: [],
            }}
          />
        ),
      },
    ],
    "/",
  );
}

describe("SearchPreferencesForm job levels", () => {
  it("scores all levels when none is picked and unchecks that once a level is chosen", async () => {
    renderForm([]);

    expect(screen.getByRole("checkbox", { name: "All levels" })).toBeChecked();
    await userEvent.click(screen.getByRole("checkbox", { name: "Mid-level" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Senior" }));

    expect(screen.getByRole("checkbox", { name: "All levels" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Mid-level" })).toBeChecked();
  });

  it("saves the chosen levels with the search settings", async () => {
    let saved: unknown = null;
    server.use(
      http.put("*/api/v1/search-preferences", async ({ request }) => {
        saved = await request.json();
        return ok({
          source: "user",
          config: { adzuna, target_levels: ["mid"], work_modes: [], exclude_title_words: [], knockouts: [] },
        });
      }),
    );
    renderForm(["mid", "senior"]);

    await userEvent.click(screen.getByRole("checkbox", { name: "Senior" }));
    await userEvent.click(screen.getByRole("button", { name: "Save preferences" }));

    await waitFor(() => expect(saved).not.toBeNull());
    expect((saved as { target_levels: string[] }).target_levels).toEqual(["mid"]);
  });

  it("returns to all levels when All levels is chosen again", async () => {
    renderForm(["senior"]);

    await userEvent.click(screen.getByRole("checkbox", { name: "All levels" }));

    expect(screen.getByRole("checkbox", { name: "Senior" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "All levels" })).toBeChecked();
  });
});
