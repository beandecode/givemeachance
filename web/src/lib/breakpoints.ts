import { useSyncExternalStore } from "react";

/** Same values as Tailwind's default breakpoints; the layouts in CSS and the ones chosen in code must agree. */
export const BREAKPOINTS = { sm: 640, md: 768, lg: 1024, xl: 1280, "2xl": 1536 } as const;
export type Breakpoint = keyof typeof BREAKPOINTS;

export const minWidth = (name: Breakpoint) => `(min-width: ${String(BREAKPOINTS[name])}px)`;

/** Live result of a CSS media query. Use it to render one of two heavy layouts instead of hiding one with CSS. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (notify) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", notify);
      return () => list.removeEventListener("change", notify);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** True from the given breakpoint upwards (`useBreakpoint("lg")` is true on a 1024 px or wider window). */
export function useBreakpoint(name: Breakpoint): boolean {
  return useMediaQuery(minWidth(name));
}
