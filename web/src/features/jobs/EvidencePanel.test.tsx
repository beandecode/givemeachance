import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EvidencePanel, readClaims } from "./EvidencePanel";

const claims = [
  { text: "Python", status: "supported", profile_path: "core_skills[0]", quote: "Python" },
  { text: "Ran a 50-person team", status: "unsupported", profile_path: "", quote: "" },
];

describe("EvidencePanel", () => {
  it("lists unsupported claims first and says how many were not found", () => {
    render(<EvidencePanel evidenceMap={{ claims }} />);

    expect(screen.getByText(/2 claims checked against your profile, 1 not found/)).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Ran a 50-person team");
    expect(items[0]).toHaveTextContent("Not in your profile");
    expect(items[1]).toHaveTextContent("core_skills[0]");
  });

  it("shows nothing for documents without a fact check", () => {
    const { container } = render(<EvidencePanel evidenceMap={{ warnings: ["x"] }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("ignores malformed claims", () => {
    expect(
      readClaims({ claims: [null, 3, { text: "x", status: "bogus" }, { text: "ok", status: "inferred" }] }),
    ).toEqual([{ text: "ok", status: "inferred", profile_path: "", quote: "" }]);
  });
});
