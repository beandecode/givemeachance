import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderRoute } from "@/test/render";

import { MatchCard } from "./MatchCard";

const match = {
  total_score: 72,
  match_score: 72,
  dimension_scores: { skills_match: 80 },
  match_reasons: [],
  strengths: [],
  gaps: [],
  risk_flags: [],
  recommendation_level: "yes",
  confidence: "high",
  missing_information: [],
  fit_reason: "",
  should_apply: true,
  model_name: "mock",
  created_at: "2026-10-01T00:00:00Z",
  source_profile_id: 1,
  source_profile_version: 1,
};

describe("MatchCard", () => {
  it("shows the years the posting asks for beside the score", () => {
    renderRoute(
      [
        {
          path: "/jobs/1",
          element: <MatchCard jobId={1} match={match} usesLatestProfile yearsAsked="Asks for 5+ years" />,
        },
      ],
      "/jobs/1",
    );

    expect(screen.getByRole("img", { name: "Match score 72 out of 100" })).toBeInTheDocument();
    expect(screen.getByText("Asks for 5+ years")).toBeInTheDocument();
  });

  it("still shows the years before the job is scored", () => {
    renderRoute(
      [
        {
          path: "/jobs/1",
          element: (
            <MatchCard jobId={1} match={null} usesLatestProfile={false} yearsAsked="Asks for 3 to 5 years" />
          ),
        },
      ],
      "/jobs/1",
    );

    expect(screen.getByText("Asks for 3 to 5 years")).toBeInTheDocument();
  });
});
