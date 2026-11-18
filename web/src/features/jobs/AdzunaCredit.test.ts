import { describe, expect, it } from "vitest";

import { fromAdzuna } from "./AdzunaCredit";

describe("fromAdzuna", () => {
  it("credits only listings that link to the job board", () => {
    expect(fromAdzuna({ source: "adzuna", url: "https://www.adzuna.ca/details/1" })).toBe(true);
    expect(fromAdzuna({ source: "adzuna", url: "https://example.com/jobs/1" })).toBe(false); // sample data
    expect(fromAdzuna({ source: "manual", url: "https://www.adzuna.ca/details/1" })).toBe(false);
    expect(fromAdzuna({ source: "adzuna", url: "" })).toBe(false);
  });
});
