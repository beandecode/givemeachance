import { describe, expect, it } from "vitest";

import { fromDraft, toDraft } from "./editModel";

const original = {
  identity: { name: "Alex", current_title: "unknown", contact: { email: "a@example.com", links: [] } },
  core_skills: ["Python", "SQL"],
  experiences: [
    { title: "Engineer", company: "Acme", highlights: ["Shipped X"], achievements: ["Cut latency 40%"] },
  ],
  education: [{ school: "U of T", degree: "BSc" }],
  missing_information: [{ field: "education", question: "Where did you study?", priority: "medium" }],
  model_name: "gemini",
};

describe("profile edit model", () => {
  it("shows placeholders as empty fields", () => {
    expect(toDraft(original).current_title).toBe("");
    expect(toDraft(original).education).toBe("U of T · BSc");
  });

  it("keeps fields the form doesn't edit", () => {
    const saved = fromDraft(original, {
      ...toDraft(original),
      name: "Alex Rivera",
      core_skills: "Python, SQL, AWS",
    });
    expect(saved.model_name).toBe("gemini");
    expect(saved.missing_information).toEqual(original.missing_information);
    expect(saved.core_skills).toEqual(["Python", "SQL", "AWS"]);
    expect((saved.identity as { name: string }).name).toBe("Alex Rivera");
    const experience = (saved.experiences as Record<string, unknown>[])[0];
    expect(experience?.achievements).toEqual(["Cut latency 40%"]);
  });

  it("leaves structured entries alone unless their text changed", () => {
    const unchanged = fromDraft(original, toDraft(original));
    expect(unchanged.education).toEqual(original.education);
    const changed = fromDraft(original, { ...toDraft(original), education: "MIT · MSc" });
    expect(changed.education).toEqual(["MIT · MSc"]);
  });
});
