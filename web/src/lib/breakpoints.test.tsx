import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { mockViewport } from "@/test/viewport";

import { BREAKPOINTS, minWidth, useBreakpoint } from "./breakpoints";

function Probe() {
  const lg = useBreakpoint("lg");
  const md = useBreakpoint("md");
  return <p>{`${md ? "md" : "small"} ${lg ? "lg" : "below-lg"}`}</p>;
}

describe("breakpoints", () => {
  it("uses Tailwind's widths", () => {
    expect(BREAKPOINTS).toEqual({ sm: 640, md: 768, lg: 1024, xl: 1280, "2xl": 1536 });
    expect(minWidth("lg")).toBe("(min-width: 1024px)");
  });

  it("follows the window width live", () => {
    mockViewport(390);
    render(<Probe />);
    expect(screen.getByText("small below-lg")).toBeInTheDocument();

    act(() => mockViewport(800));
    expect(screen.getByText("md below-lg")).toBeInTheDocument();

    act(() => mockViewport(1440));
    expect(screen.getByText("md lg")).toBeInTheDocument();

    act(() => mockViewport(1023));
    expect(screen.getByText("md below-lg")).toBeInTheDocument();
  });
});
