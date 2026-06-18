/**
 * Base path prefix for serving DigiChat under a subpath (e.g. digithings.ai/chat).
 *
 * Empty by default → the app serves at root (self-host `make up-digichat`, local
 * dev, and the legacy chat.digithings.ai deploy are all unaffected). Set
 * NEXT_PUBLIC_DIGICHAT_BASE_PATH=/chat at build time (alongside DIGICHAT_BASE_PATH
 * for next.config's basePath) to serve under /chat.
 *
 * Next's <Link>/router auto-prefix basePath, but raw fetch() to "/api/..." and
 * next-auth/react's signIn/signOut callbackUrls do NOT — prefix those with BASE_PATH.
 */
export const BASE_PATH = process.env.NEXT_PUBLIC_DIGICHAT_BASE_PATH ?? "";

/** Prefix an app-absolute path with the base path. `p("/api/x")` → "/api/x" or "/chat/api/x". */
export const p = (path: string): string => `${BASE_PATH}${path}`;
