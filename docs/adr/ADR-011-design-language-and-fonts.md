# ADR-011: A calm navy design language, fonts self-hosted, phone and desktop equal

Date: 2026-10-25
Status: Superseded by [ADR-012](ADR-012-neon-glass-design-language.md) (visual language and fonts); the phone and desktop rules and the test matrix still apply

## Context

The first web app looked like a generic web-app template: blue accent, bordered cards with shadows, coloured pills on every
fact, tiny capital-letter headings. The target was the calm, confident feel of Wealthsimple's iOS app (principles
only, no assets) and for phone and desktop to be treated as equally important. Constraints that stay: strict CSP
(`font-src 'self'`, `style-src 'self'`), no UI library (ADR-008), no new runtime dependency, routes and API unchanged.

## Decision

- **Direction:** deep navy brand colour, a quiet canvas, large serif headlines and numbers, space instead of borders.
  Hierarchy comes from (1) whitespace, (2) soft fills, (3) a 1px border only where a surface sits on a surface of the
  same colour (the document "paper", focus rings), (4) a shadow only on floating layers (dialogs, toasts, the task
  tray, a dragged card, the phone action bar).
- **Tokens in one place:** `web/src/index.css` holds colours (light and dark), type scale, radii and motion in a
  Tailwind `@theme` block. Dark mode follows the system. `tokens.test.ts` checks WCAG contrast of every colour pair,
  and Playwright runs axe in light and dark at every size.
- **Fonts:** Figtree (variable, has tabular figures) for text and Instrument Serif for headlines at 28px and up and for
  the big score numbers. Both are SIL OFL 1.1, subset to Latin (45 KB of WOFF in total), self-hosted under
  `web/src/assets/fonts/` with their licences. `font-display: swap` with size-matched fallbacks; no preload, because
  Vite hashes the file names. Instrument Serif has no tabular figures, so scores sit in a fixed-width box.
- **Phone and desktop are both first-class:** breakpoints are Tailwind's (640, 768, 1024, 1280, 1536) and a shared
  constant for the places that choose a layout in code (`useBreakpoint`). Heavy alternatives render one version only:
  the application board from 1024 px and stage tabs below it; the next-step action in a bar above the tab bar below
  1024 px and in the side column above it; filters in a side panel from 1280 px, an inline panel from 768 px and a
  bottom sheet on phones. Dialogs are bottom sheets on phones. Touch targets are at least 44px.
- **Pages choose their own width** (reading pages stay at 72rem, the board uses up to 100rem and shows its eight
  stages as two rows of four from 1536 px, so nothing scrolls sideways).
- **Test matrix:** desktop 1280, phone (Pixel 7), tablet 768, wide 1920, each with axe; dark mode on desktop and phone.

## Consequences

1. Fewer visual primitives: `Badge` pills became `Dot` and `Meta` text, `Card` has no border or shadow, `ScoreRing`
   became `Score` (serif number, ring only on the job page).
2. Every new screen needs a loading, empty and error state in this style; unit tests use a stubbed `matchMedia`
   (`src/test/viewport.ts`) because jsdom does not load Tailwind.
3. Changing the palette or fonts is a one-file change plus the contrast test.
4. The two font files add 45 KB to the first load; a missing font only falls back to the system font.
