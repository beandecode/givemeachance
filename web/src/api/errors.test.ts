import { describe, expect, it } from "vitest";

import { ApiError } from "./client";
import { describeError } from "./errors";

describe("describeError", () => {
  it("explains known codes and keeps the support reference", () => {
    const error = new ApiError(429, { error_code: 1005, message: "locked", correlation_id: "req_1" }, "");
    expect(describeError(error)).toEqual({
      message: "Too many failed sign-in attempts. Wait 15 minutes, then try again.",
      reference: "req_1",
    });
  });

  it("explains the read-only demo", () => {
    const error = new ApiError(403, { error_code: 1004, message: "demo", correlation_id: "req_2" }, "");
    expect(describeError(error).message).toBe("This is a read-only demo, so changes are turned off.");
  });

  it("lists field problems for validation errors", () => {
    const error = new ApiError(
      400,
      {
        error_code: 2002,
        message: "invalid",
        details: [{ field: "body.salary_min", message: "must be ≥ 0" }],
      },
      "",
    );
    expect(describeError(error).message).toBe("Salary min: must be ≥ 0");
  });

  it("never shows server internals for 5xx", () => {
    const error = new ApiError(
      500,
      { error_code: 5001, message: "Traceback ...", correlation_id: "req_2" },
      "",
    );
    expect(describeError(error).message).toMatch(/Something went wrong on our side/);
  });

  it("handles network failures and unknown values", () => {
    expect(describeError(new ApiError(0, null, "network error")).message).toMatch(/Can't reach the server/);
    expect(describeError(new Error("boom")).message).toBe("Something went wrong. Please try again.");
  });
});
