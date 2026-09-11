/**
 * Web search preference (default ON; tenant-gated).
 *
 * Default on. Tenant must still allow (`webSearch: true` in config) — that gate
 * is unchanged (#3420): the BFF only sends X-Digi-Enable-Web-Search when the
 * tenant allows AND this user pref is on. The user opts out via this
 * localStorage flag, persisted as "0". Callers pass `defaultOn: false` only
 * for surfaces that stay default-off.
 */

const STORAGE_PREFIX = "digichat-web-search:";

export function webSearchStorageKey(scope: string): string {
  const s = scope.trim() || "default";
  return `${STORAGE_PREFIX}${s}`;
}

/**
 * Read user preference. Missing key → `defaultOn` (true unless the caller
 * opts a surface into default-off). Explicit "0" always opts out.
 */
export function readWebSearchPref(scope: string, defaultOn = true): boolean {
  if (typeof window === "undefined") return false;
  try {
    const stored = window.localStorage.getItem(webSearchStorageKey(scope));
    if (stored === null) return defaultOn;
    return stored !== "0";
  } catch {
    return false;
  }
}

export function writeWebSearchPref(scope: string, enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    const key = webSearchStorageKey(scope);
    if (enabled) window.localStorage.setItem(key, "1");
    else window.localStorage.setItem(key, "0");
  } catch {
    /* private mode / quota */
  }
}

/**
 * Effective enable for a request: tenant must allow AND user must not opt out.
 * Either false → do not send the digigraph header.
 */
export function isWebSearchEnabled(args: {
  tenantAllows: boolean;
  userPref: boolean;
}): boolean {
  return args.tenantAllows === true && args.userPref === true;
}
