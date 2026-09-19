/**
 * How long the OAuth PKCE callback waits for the session exchange before it
 * surfaces the sign-in-failed state. Lives outside `page.tsx` because Next's
 * App-Router page-export check rejects non-page exports from a page module.
 */
export const AUTH_CALLBACK_SETTLE_MS = 8_000;
