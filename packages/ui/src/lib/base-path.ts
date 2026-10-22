/**
 * The base path the digichat app is served under (DIG-5121).
 *
 * The digichat app is served under `/chat` on digithings.ai. This package is
 * shared with the marketing sites, which are served at the root, so the base
 * path is EMPTY by default and only the digichat build carries one.
 *
 * The value comes from the same build-time variable the app reads
 * (`NEXT_PUBLIC_DIGICHAT_BASE_PATH`): Next inlines `NEXT_PUBLIC_*` into every
 * module of the bundle, so the browser gets the value the app was built with.
 * The app's own copy lives in apps/digichat/src/lib/base-path.ts and reads
 * the same variable — one value, two names for it, never two values.
 *
 * Why this file exists: the shared components make calls into the app's own
 * API (the artifacts panel is the one that matters), and a root-absolute
 * path ("/api/conversations/…") works while the app is at the root and 404s
 * the moment it is served under a base path.
 */

/**
 * The base path, or "" when the app is served at the root.
 *
 * Normalised the same way the app's own copy is (no trailing slash), so the
 * two helpers always produce the same path for the same input.
 *
 * The read is the same one the app's own copy does (apps/digichat/src/lib/
 * base-path.ts), and for the same reason: `process.env.NEXT_PUBLIC_*` is
 * inlined into the bundle by the framework, so the browser gets the value the
 * app was built with. It is NOT guarded by `typeof process` on purpose — a
 * guard that reads "process is missing" in the browser would swallow the
 * inlined value and silently serve the app at the root, which is exactly the
 * bug this file exists to prevent.
 */
export const BASE_PATH: string = (process.env.NEXT_PUBLIC_DIGICHAT_BASE_PATH ?? "")
  .trim()
  .replace(/\/+$/, "");

/**
 * Prefix a path with the base path.
 *
 * The one way to write a path into the app from this package. A root-relative
 * path that skips it breaks under a base path.
 */
export function p(path: string): string {
  return `${BASE_PATH}${path}`;
}

/**
 * The path without the base path.
 *
 * The mirror of `p`: a URL the app produced (already prefixed) has to be
 * turned back into the app's own path before it can be matched against the
 * app's route shape. With no base path this is the identity.
 */
export function stripBasePath(path: string): string {
  if (!BASE_PATH) return path;
  if (path === BASE_PATH) return "/";
  if (path.startsWith(`${BASE_PATH}/`)) return path.slice(BASE_PATH.length);
  return path;
}
