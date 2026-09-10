"use client";

/**
 * Web search preference synced after mount.
 *
 * First render is always `false` so server and client markup agree
 * (no hydration mismatch); an effect then syncs the stored/default-ON
 * value. The setter persists via localStorage and updates state.
 */
import { useCallback, useEffect, useState } from "react";
import { readWebSearchPref, writeWebSearchPref } from "@/lib/web-search-pref";

export function useSyncedWebSearchPref(scope: string): [boolean, (next: boolean) => void] {
  const [pref, setPref] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional one-shot mount sync: first render must match SSR (false) to avoid a hydration mismatch; the stored/default-ON value applies after mount.
    setPref(readWebSearchPref(scope));
  }, [scope]);
  const set = useCallback(
    (next: boolean) => {
      writeWebSearchPref(scope, next);
      setPref(next);
    },
    [scope],
  );
  return [pref, set];
}
