import { useEffect } from "react";

import { usePreferences } from "@/api/queries";

/** Applies the saved glass level to <html data-gi>; "auto" leaves it off so light mode is strong and dark is medium. */
export function useGlassLevel() {
  const level = usePreferences().data?.ui.glass ?? "auto";
  useEffect(() => {
    const root = document.documentElement;
    if (level === "auto") delete root.dataset.gi;
    else root.dataset.gi = level;
  }, [level]);
}
