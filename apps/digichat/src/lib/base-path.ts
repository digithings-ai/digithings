/**
 * Base path prefix for serving digichat under a subpath (e.g. digithings.ai/chat).
 *
 * Empty by default → the app serves at root (self-host `make up-digichat`, local
 * dev, and the legacy chat.digithings.ai deploy are all unaffected). Set
 * NEXT_PUBLIC_DIGICHAT_BASE_PATH=/chat at build time (alongside DIGICHAT_BASE_PATH
 * for next.config's basePath) to serve under /chat.
 *
 * Next's <Link>/router auto-prefix basePath, but raw fetch() to "/api/..." and
 * next-auth/react's signIn/signOut callbackUrls do NOT — prefix those with BASE_PATH.
 */
/**
 * The base path prefix, normalised: no trailing slash, so `p("/api/x")` is
 * "/chat/api/x" and never "/chat//api/x". next.config.ts compares the two
 * base-path names after the same normalisation, so the server and the client
 * always agree on the value (DIG-5121).
 */
export const BASE_PATH = (process.env.NEXT_PUBLIC_DIGICHAT_BASE_PATH ?? "").trim().replace(/\/+$/, "");

/** Prefix an app-absolute path with the base path. `p("/api/x")` → "/api/x" or "/chat/api/x". */
export const p = (path: string): string => `${BASE_PATH}${path}`;
