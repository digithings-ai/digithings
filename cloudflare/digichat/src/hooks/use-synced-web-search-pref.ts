"use client";

/**
 * Web search preference synced after mount.
 *
 * First render is always `false` so server and client markup agree
 * (no hydration mismatch); an effect then syncs the stored value, falling
 * back to `defaultOn` when nothing is stored. Pass `defaultOn: true` only
 * for the baseline embed surface (slug "embed"); everywhere else the
 * default stays off so prior opt-outs are never silently re-enabled
 * (#3420). The setter persists via localStorage and updates state.
 */
import { useCallback, useEffect, useState } from "react";
import { readWebSearchPref, writeWebSearchPref } from "@/lib/web-search-pref";

export function useSyncedWebSearchPref(
  scope: string,
  defaultOn = false,
): [boolean, (next: boolean) => void] {
  const [pref, setPref] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional one-shot mount sync: first render must match SSR (false) to avoid a hydration mismatch; the stored/default value applies after mount.
    setPref(readWebSearchPref(scope, defaultOn));
  }, [scope, defaultOn]);
  const set = useCallback(
    (next: boolean) => {
      writeWebSearchPref(scope, next);
      setPref(next);
    },
    [scope],
  );
  return [pref, set];
}
