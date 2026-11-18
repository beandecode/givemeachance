# ADR-012: Neon Glass design language (supersedes ADR-011)

Date: 2026-10-25
Status: Accepted

## Context

ADR-011 gave the app a calm navy look with serif headlines. The brief was a complete redesign around a swipe
screen for scored jobs (ADR-013) with a bolder identity: the Harbor slate and teal base, a yellow cyberpunk HUD
influence, and Apple's Liquid Glass material on the framing surfaces. Three directions were mocked up and compared on
phone and desktop in light and dark; "Harbor Neon" with extra glass was chosen. Constraints that stay: strict CSP
(`font-src 'self'`, `style-src 'self'`), no UI library (ADR-008), no new runtime dependency, phone and desktop equal.

## Decision

- **Identity:** Harbor slate and teal ground, signal yellow as the lead accent, HUD details (corner brackets, one cut
  corner per panel, faint grid and scanlines behind screens), translucent glass for every framing surface. Yellow is
  always a fill with dark ink; yellow is text only on dark backgrounds (it is 1.11:1 on the light ground).
- **Glass material:** `backdrop-filter: blur() saturate()` over a tinted translucent fill, a bright rim on the top and
  left edges, an inner glow, a faint diagonal sheen that follows a dragged card, and small text on a denser inner
  "plate" (84 to 90% opaque) so reading never depends on what is behind the blur. Panels that clip a corner with
  `clip-path` lose their outer drop shadow; their depth comes from rim and glow.
- **Glass intensity** is four CSS variable sets (below) applied on `<html data-gi>`. The setting is a user preference
  (`ui.glass`, ADR-013): `auto` (default) = Medium in dark mode and Strong in light mode, or a fixed Subtle / Medium /
  Medium+ / Strong. Strong costs the most (large blurred layers re-render while dragging); the setting exists so a slow
  phone can turn it down.
- **Accessibility fallbacks:** `prefers-reduced-transparency`, and browsers without `backdrop-filter`, switch every
  glass surface to an opaque solid with the rims, brackets and yellow kept; `prefers-reduced-motion` stops the scan
  sweep, ambient light motion and transitions. Contrast is checked by `tokens.test.ts` for every text pair, including
  the worst case of Strong glass over the brightest backdrop light. Playwright runs axe in light, dark and opaque mode.
- **Fonts (self-hosted, SIL OFL, Latin subset WOFF2 under `web/src/assets/fonts/` with licences):** Chakra Petch
  600/700 for display, scores, labels and stamps (set in capitals for labels); Manrope for text; JetBrains Mono for
  counts, meta and key hints. `font-display: swap` with size-matched fallbacks, no preload. Figtree and Instrument
  Serif are removed.
- **Style code stays CSP-safe:** no inline `style` attributes in markup. Dynamic values (drag offset, glass variables)
  are set through the CSSOM (`element.style.setProperty`, React's `style` prop) or classes.
- **Tokens** live in the `@theme` block of `web/src/index.css`, light and dark, plus the glass variable sets:

| Token | Light | Dark | Use |
|---|---|---|---|
| page ground | #D0DAE0 | #0B161B | Behind everything |
| screen ground | #C6D2D8 | #071116 | Under the glass |
| ink | #0F1B21 | #E8F1F2 | Text, icons, HUD brackets |
| muted | #34444D | #93A7B0 | Secondary text, labels |
| line | ink at 16% | yellow at 16% | Hairlines, dividers |
| teal fill | #0B6E77 | #4FC1CB | Match bars |
| teal text | #075A62 | #4FC1CB | Waitlist cue, focus ring |
| signal yellow | #F5DC1F | #F7E14B | Score plate, main button, active tab, stamp (fill only) |
| ink on yellow | #0F1B21 | #0B1114 | Text on yellow |
| skip | #9A3626 | #FF8F80 | Skip, missing skills |
| waitlist | #075A62 | #5CCBD4 | Waitlist |
| details | #34444D | #B7C7CE | Details |
| glass tint | #F0F6F8 | #0C1C23 | Alpha from the intensity set |
| opaque panel / plate | #EDF2F4 / #E2E9ED | #0E1D24 / #13262E | Fallback surfaces |
| glass edge | white at 70% | yellow at 22% | Rim line |

| Glass level | Blur | Saturate | Panel alpha | Rim | Plate alpha |
|---|---|---|---|---|---|
| Subtle | 8px | 125% | .80 | .55 | .90 |
| Medium | 16px | 150% | .64 | .80 | .88 |
| Medium+ | 24px | 175% | .54 | .95 | .86 |
| Strong | 34px | 200% | .40 | 1.0 | .84 |

| Type role | Face | Size / line | Use |
|---|---|---|---|
| Display | Chakra Petch 700, caps | 30 / 1.1 | Screen titles |
| Score | Chakra Petch 700 | 52 / 1 | Match score on the yellow plate |
| Title | Chakra Petch 700 | 23 / 1.12 | Job title |
| Body | Manrope 500 | 14 / 1.5 | Running text |
| Small | Manrope 500 to 600 | 12.5 / 1.45 | Reasons, meta, résumé preview |
| Label | Chakra Petch 600 to 700, caps | 11 to 13 / 1.3 | Tabs, chips, section labels |
| Data | JetBrains Mono 500 | 11 to 13 / 1.4 | Counts, company line, key hints |
| Stamp | Chakra Petch 700, caps | 19 / 1 | Swipe stamps |

Measured contrast (WCAG 2.x): ink on yellow 12.63:1 light, 14.33:1 dark; ink on ground 11.35:1 / 16.62:1; muted on
ground 6.54:1 / 7.63:1; teal text on Strong glass over the brightest light 4.81:1 (light); muted on Strong glass in
the same worst case 6.12:1 / 5.49:1.

## Alternatives considered

- **Harbor Glass** (glass-first, yellow only as a small signal) and **Harbor Fusion** (clear glass over drifting teal
  and yellow light, most atmospheric, heaviest on older phones) were mocked up and are kept as reference, not built.
- Keeping the ADR-011 navy/serif look: rejected (a new identity was wanted).

## Consequences

1. Every screen is rebuilt on the new tokens; `Score`, `Card`, `Dialog`, `Button`, `SegmentedControl` and the shell are
   reskinned, `Meta`/`Dot` stay.
2. Glass costs GPU time: phone testing on the localtest stack decides the shipping default; the intensity setting is
   the escape hatch, and the opaque path must always look good.
3. Instrument Serif and Figtree are deleted from `web/src/assets/fonts/`; the font licence files are replaced.
4. ADR-011 is marked superseded; its test matrix (1280, Pixel 7, 768, 1920, axe light and dark) stays and gains an
   opaque-mode run.
