"use client";

/**
 * Web search preference synced after mount.
 *
 * First render is always `false` so server and client markup agree
 * (no hydration mismatch); an effect then syncs the stored value, falling
 * back to `defaultOn` (on) when nothing is stored. Explicit stored "0"
 * always opts out. The tenant AND-gate lives at the callers
 * (`isWebSearchEnabled`): this hook returns the user pref only, so a deny
 * tenant stays off regardless of the default. Pass `defaultOn: false`
 * only for surfaces that stay default-off.
 */
import { useCallback, useEffect, useState } from "react";
import { readWebSearchPref, writeWebSearchPref } from "@/lib/web-search-pref";

export function useSyncedWebSearchPref(
  scope: string,
  defaultOn = true,
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
