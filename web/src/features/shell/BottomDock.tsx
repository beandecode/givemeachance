import type { ReactNode } from "react";
import { createContext, useContext } from "react";
import { createPortal } from "react-dom";

/** The element inside the phone dock that pages may fill with a bar of their own (null on wide screens). */
export const BottomDockContext = createContext<HTMLElement | null>(null);

/**
 * Puts a page bar (like "Next step") into the dock above the tab bar, so the two are one block that cannot
 * leave a gap between them. Renders nothing where there is no dock (from 1024 px).
 */
export function BottomDock({ children }: { children: ReactNode }) {
  const slot = useContext(BottomDockContext);
  return slot ? createPortal(children, slot) : null;
}
