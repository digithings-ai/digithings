/**
 * Invite-key resolution for the /chat/occ invite link (DIG-1210).
 *
 * The OCC chat is served to the public, so the key in the parent URL is the only
 * thing between a passing visitor and a tenant that can quote unmasked customer
 * data. It is deliberately the *same* `token` key digichat already understands
 * (`X-Embed-Token`, read in `embed-client.tsx`), passed through under one name:
 * a second name for one secret is a support burden and an operator-error surface.
 *
 * Bearer capability, NOT authentication. digichat treats the embed token as a
 * publishable key that is rendered into the embedding page on purpose
 * (apps/digichat/ARCHITECTURE.md, DIG-619), so anyone who holds the link can
 * open the chat. What the link buys is that the page is no longer open to every
 * visitor who finds it — the barrier that was asked for.
 */

/** Query key carrying the invite token, on the parent URL and on the embed URL. */
export const INVITE_TOKEN_PARAM = "token";

/**
 * Read the invite token out of a parent URL query string.
 *
 * Always called with the live `window.location.search`, never with a value baked
 * into the page: this app is `output: "export"`, so the HTML is one static
 * artifact shared by every visitor. A key baked into it would be handed to
 * whoever loads the page next.
 *
 * Returns undefined for a missing, empty or whitespace-only value so the caller
 * forwards no `token=` at all rather than a blank one — `token=` present but
 * empty would still look like an attempted invite to digichat's log readers.
 */
export function readInviteToken(search: string | undefined): string | undefined {
  if (!search) return undefined;
  const raw = new URLSearchParams(search).get(INVITE_TOKEN_PARAM);
  if (raw === null) return undefined;
  const trimmed = raw.trim();
  return trimmed === "" ? undefined : trimmed;
}

/**
 * Remove the invite key from the address bar once it has been read (DIG-1437).
 *
 * An unstripped key lands in browser history and stays visible to anyone
 * reading over a shoulder. The Worker gate accepts the matching occ_invite
 * cookie after the key leaves the address bar (DIG-1437).
 *
 * Returns the cleaned URL, or null when there is nothing to strip — a missing,
 * empty or whitespace-only param is a no-op, which keeps readInviteToken the
 * single reader and leaves an ordinary /chat visit without rewriting its own
 * history. Every other query param and the hash are preserved.
 */
export function stripInviteTokenFromUrl(href: string): string | null {
  const url = new URL(href);
  const raw = url.searchParams.get(INVITE_TOKEN_PARAM);
  if (raw === null || raw.trim() === "") return null;
  url.searchParams.delete(INVITE_TOKEN_PARAM);
  return url.toString();
}
