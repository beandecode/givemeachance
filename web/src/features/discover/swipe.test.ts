import { describe, expect, it } from "vitest";

import { COMMIT_DISTANCE, directionOf, releaseDirection } from "./swipe";

describe("directionOf", () => {
  it("is null until the drag is long enough", () => {
    expect(directionOf(COMMIT_DISTANCE - 1, 10)).toBeNull();
    expect(directionOf(0, 0)).toBeNull();
  });

  it("follows the dominant axis", () => {
    expect(directionOf(120, 30)).toBe("right");
    expect(directionOf(-120, 30)).toBe("left");
    expect(directionOf(20, -140)).toBe("up");
    expect(directionOf(-20, 140)).toBe("down");
  });
});

describe("releaseDirection", () => {
  it("commits a long slow drag", () => {
    expect(releaseDirection(150, 0, 1500)).toBe("right");
  });

  it("commits a short fast flick but not a short slow movement", () => {
    expect(releaseDirection(-60, 5, 60)).toBe("left");
    expect(releaseDirection(-60, 5, 600)).toBeNull();
  });

  it("ignores a tap", () => {
    expect(releaseDirection(2, 1, 80)).toBeNull();
  });
});
