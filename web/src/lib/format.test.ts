import { describe, expect, it } from "vitest";

import { formatSalary, isBlank, recommendationLabel, scoreTone, textList, yearsAskedLabel } from "./format";

describe("format helpers", () => {
  it("treats model placeholders as blank", () => {
    expect(isBlank("unknown")).toBe(true);
    expect(isBlank(" N/A ")).toBe(true);
    expect(isBlank(["", "none"])).toBe(true);
    expect(isBlank("Toronto")).toBe(false);
    expect(textList(["Python", "unknown", 3, " SQL "])).toEqual(["Python", "SQL"]);
  });

  it("formats salary ranges compactly", () => {
    expect(formatSalary(85000, 110000)).toBe("85k–110k");
    expect(formatSalary(90000, null)).toBe("from 90k");
    expect(formatSalary(null, null)).toBe("");
  });

  it("maps scores and recommendation levels to user-facing labels", () => {
    expect(scoreTone(90)).toBe("good");
    expect(scoreTone(60)).toBe("warn");
    expect(scoreTone(20)).toBe("bad");
    expect(scoreTone(null)).toBe("none");
    expect(recommendationLabel("strong_yes")).toBe("Strong match");
    expect(recommendationLabel("something_else")).toBe("");
  });

  it("names the years a posting asks for", () => {
    expect(yearsAskedLabel(5, null)).toBe("Asks for 5+ years");
    expect(yearsAskedLabel(3, 5)).toBe("Asks for 3 to 5 years");
    expect(yearsAskedLabel(1, undefined)).toBe("Asks for 1+ year");
    expect(yearsAskedLabel(null, null)).toBe("");
  });
});
