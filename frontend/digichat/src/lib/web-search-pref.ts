/**
 * Opt-in web search preference (#3420).
 *
 * Default off. Tenant must allow (`webSearch: true` in DIGICHAT_EMBED_TENANTS);
 * the user must also opt in via this localStorage flag. Both are required before
 * the BFF sends X-Digi-Enable-Web-Search — never silently mix web into RAG.
 */

const STORAGE_PREFIX = "digichat-web-search:";

export function webSearchStorageKey(scope: string): string {
  const s = scope.trim() || "default";
  return `${STORAGE_PREFIX}${s}`;
}

/** Read user preference; missing/invalid → false (default off). */
export function readWebSearchPref(scope: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(webSearchStorageKey(scope)) === "1";
  } catch {
    return false;
  }
}

export function writeWebSearchPref(scope: string, enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    const key = webSearchStorageKey(scope);
    if (enabled) window.localStorage.setItem(key, "1");
    else window.localStorage.removeItem(key);
  } catch {
    /* private mode / quota */
  }
}

/**
 * Effective enable for a request: tenant must allow AND user must opt in.
 * Either false → do not send the digigraph header.
 */
export function isWebSearchEnabled(args: {
  tenantAllows: boolean;
  userPref: boolean;
}): boolean {
  return args.tenantAllows === true && args.userPref === true;
}
