import { screen } from "@testing-library/react";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { ok, server } from "@/test/server";
import { renderRoute } from "@/test/render";

import { DocumentPanel, documentWarnings } from "./DocumentPanel";

const summary = {
  id: 5,
  version: 1,
  created_at: "2026-10-25T00:00:00Z",
  source_profile_id: 1,
  origin: "generated" as const,
  version_count: 1,
};

function document(evidenceMap: Record<string, unknown>) {
  return {
    id: 5,
    kind: "resume",
    job_id: 1,
    version: 1,
    content_md: "# Casey Chen\n\nBuilt APIs.",
    evidence_map: evidenceMap,
    source_profile_id: 1,
    created_at: "2026-10-25T00:00:00Z",
    origin: "generated",
  };
}

function show(evidenceMap: Record<string, unknown>) {
  server.use(
    http.get("*/api/v1/jobs/1/documents", () =>
      ok({ resume: [{ ...summary, length: 20 }], cover_letter: [] }),
    ),
    http.get("*/api/v1/documents/resume/5", () => ok(document(evidenceMap))),
  );
  renderRoute(
    [{ path: "/", element: <DocumentPanel jobId={1} kind="resume" latest={summary} canGenerate /> }],
    "/",
  );
}

describe("DocumentPanel warnings", () => {
  it("lists what the app found wrong in the generated text", async () => {
    show({
      mode: "llm",
      warnings: ["These numbers are not in your profile or the posting, please check them: 300"],
    });

    expect(await screen.findByText("Check this before you send it")).toBeInTheDocument();
    expect(screen.getByText(/please check them: 300/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Casey Chen" })).toBeInTheDocument();
  });

  it("shows nothing extra for a clean document", async () => {
    show({ mode: "llm" });

    expect(await screen.findByRole("heading", { name: "Casey Chen" })).toBeInTheDocument();
    expect(screen.queryByText("Check this before you send it")).not.toBeInTheDocument();
  });

  it("ignores anything that is not a list of strings", () => {
    expect(documentWarnings({ warnings: "nope" })).toEqual([]);
    expect(documentWarnings({ warnings: ["a", 3, null, "b"] })).toEqual(["a", "b"]);
    expect(documentWarnings(undefined)).toEqual([]);
  });
});
