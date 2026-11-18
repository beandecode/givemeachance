import { describe, expect, it } from "vitest";

import css from "../index.css?raw";

/**
 * The colour tokens in src/index.css must keep WCAG 2.1 AA contrast in light and dark mode:
 * 4.5:1 for text and 3:1 for focus rings and other UI outlines. Playwright's axe runs only see the pages
 * they visit; this checks every pair the design can produce.
 */

function block(startMarker: string): string {
  const start = css.indexOf(startMarker);
  if (start < 0) throw new Error(`index.css has no ${startMarker}`);
  const open = css.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === "{") depth++;
    if (css[i] === "}" && --depth === 0) return css.slice(open + 1, i);
  }
  throw new Error(`unclosed ${startMarker}`);
}

function colors(source: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const match of source.matchAll(/--color-([a-z-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    result[match[1] ?? ""] = match[2] ?? "";
  }
  return result;
}

const light = colors(block("@theme"));
const dark = { ...light, ...colors(block("@media (prefers-color-scheme: dark)")) };

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => {
    const value = parseInt(hex.slice(i, i + 2), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * (channels[0] ?? 0) + 0.7152 * (channels[1] ?? 0) + 0.0722 * (channels[2] ?? 0);
}

export function contrast(a: string, b: string): number {
  const [bright, dim] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((bright ?? 0) + 0.05) / ((dim ?? 0) + 0.05);
}

/** [text colour, background colour] pairs the UI uses. */
const TEXT_PAIRS: [string, string][] = [
  ["ink", "canvas"],
  ["ink", "surface"],
  ["ink", "subtle"],
  ["muted", "canvas"],
  ["muted", "surface"],
  ["muted", "subtle"],
  ["faint", "canvas"],
  ["faint", "surface"],
  ["faint", "subtle"],
  ["accent", "canvas"],
  ["accent", "surface"],
  ["accent", "accent-soft"],
  ["on-accent", "accent"],
  ["on-brand", "brand"],
  ["accent-strong", "surface"],
  ["good", "surface"],
  ["good", "good-soft"],
  ["warn", "surface"],
  ["warn", "warn-soft"],
  ["bad", "surface"],
  ["bad", "bad-soft"],
];

// Focus rings and selected states. Borders (`line`, `line-strong`) are decoration: controls are told apart by
// their fill and the focus ring, so they are deliberately not held to 3:1.
const UI_PAIRS: [string, string][] = [
  ["accent", "canvas"],
  ["accent", "surface"],
];

describe.each([
  ["light", light],
  ["dark", dark],
] as const)("%s colour tokens", (_mode, tokens) => {
  it.each(TEXT_PAIRS)("%s text on %s has at least 4.5:1", (foreground, background) => {
    const fg = tokens[foreground];
    const bg = tokens[background];
    expect(fg, `--color-${foreground}`).toBeDefined();
    expect(bg, `--color-${background}`).toBeDefined();
    expect(contrast(fg ?? "", bg ?? "")).toBeGreaterThanOrEqual(4.5);
  });

  it.each(UI_PAIRS)("%s against %s has at least 3:1 (focus rings, outlines)", (foreground, background) => {
    expect(contrast(tokens[foreground] ?? "", tokens[background] ?? "")).toBeGreaterThanOrEqual(3);
  });
});

describe("contrast()", () => {
  it("matches the WCAG reference values", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 1);
    expect(contrast("#777777", "#ffffff")).toBeCloseTo(4.48, 1);
    expect(contrast("#ffffff", "#ffffff")).toBe(1);
  });
});
