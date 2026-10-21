/**
 * Host-scoped tenant credential for the trial proof mint route (DIG-4526).
 *
 * A tenant that needs a signed trial proof for its OWN embed host calls
 * POST /api/embed/trial-proof-mint from its server-side backend and presents
 * the credential in `x-embed-tenant-mint-token`. The credential is bound to
 * ONE host: the route mints the proof for that host only, so a tenant can
 * never mint a proof for another tenant's host.
 *
 * The list lives in DIGICHAT_TENANT_MINT_CREDENTIALS as a comma separated list
 * of `host=token` pairs. It is a Worker secret, not a build value; when it is
 * absent no tenant can mint.
 *
 * This is deliberately NOT the monitor allowlist and NOT the tenant registry
 * token:
 * - the monitor allowlist (DIGICHAT_MONITOR_TOKENS) is host-unscoped, and a
 *   token on it also satisfies the quota directly in the chat route, so a
 *   tenant credential placed there could mint a proof for another tenant's
 *   host;
 * - the tenant registry token is a publishable key rendered into the embedding
 *   page on purpose, so a mint route keyed on it would be a public endpoint.
 *
 * The tenant credential therefore has its own variable and its own header, and
 * the chat route never reads it.
 *
 * HOSTS ARE COMPARED IN CANONICAL FORM. The house helper
 * `normalizeEmbedHost` is the one the consume side already uses (the chat
 * route compares `normalizeEmbedHost(proofHost)` with the canonical form of
 * `X-Embed-Host`), so the mint route compares the same thing the verifier
 * compares. A trimmed, lower-cased compare would refuse a legitimate caller
 * whose backend sends `https://tenant.example.com` while the pair holds
 * `tenant.example.com` — and the reverse. Canonicalising both sides makes the
 * round trip work in the shape callers actually use.
 */

import { normalizeEmbedHost } from "@/lib/embed-tenants";
import { safeEqualStr } from "@/lib/safe-equal";

/**
 * Header carrying the host-scoped tenant credential. Distinct from every
 * other embed header, and in particular from the monitor header: one header
 * with two meanings would make a tenant token a monitor token.
 */
export const EMBED_TENANT_MINT_TOKEN_HEADER = "x-embed-tenant-mint-token";

/**
 * Worker secret holding the `host=token` pairs. The NAME is exported so the
 * value never has to be read: a secret belongs in the environment, not in a
 * log line.
 */
export const TENANT_MINT_CREDENTIALS_ENV = "DIGICHAT_TENANT_MINT_CREDENTIALS";

/** One parsed `host=token` pair. */
type TenantMintCredential = { host: string; token: string };

/**
 * The parsed pairs of DIGICHAT_TENANT_MINT_CREDENTIALS.
 *
 * One pair is `host=token`, split at the FIRST `=` so a token may itself
 * contain one. Both sides are trimmed. A pair with no `=`, an empty host or an
 * empty token is skipped: a half-written pair must never authorise anything,
 * and it must never shadow a well-formed one.
 */
function tenantMintCredentials(): TenantMintCredential[] {
  const raw = process.env[TENANT_MINT_CREDENTIALS_ENV];
  if (!raw) return [];
  const entries: TenantMintCredential[] = [];
  for (const pair of raw.split(",")) {
    const separator = pair.indexOf("=");
    if (separator < 0) continue;
    const host = pair.slice(0, separator).trim();
    const token = pair.slice(separator + 1).trim();
    if (!host || !token) continue;
    entries.push({ host, token });
  }
  return entries;
}

/**
 * The canonical host a presented tenant credential is bound to, or null when
 * the credential authorises nothing.
 *
 * Two rules make the list trustworthy, and both refuse rather than pick:
 * - a host may appear at most once in the list;
 * - one token may not appear under two hosts.
 * A list that breaks either rule binds nothing for the host it breaks, so the
 * route refuses instead of guessing which entry was meant. The host rule is
 * checked in CANONICAL form, so a list that names one host twice in two
 * different spellings is still ambiguous.
 *
 * Compares against every entry without early exit, so neither the number of
 * comparisons nor which entry matched is observable from timing.
 */
export function tenantMintCredentialHost(presented: string | null): string | null {
  const token = presented?.trim();
  if (!token) return null;

  const entries = tenantMintCredentials();
  const matches = entries.filter((entry) => safeEqualStr(token, entry.token));
  // One token may not appear under two hosts: an ambiguous list binds nothing.
  if (matches.length !== 1) return null;
  const [matched] = matches;
  if (!matched) return null;

  // The bound host in CANONICAL form, so the proof carries the bare host the
  // consume side expects, whatever spelling the operator wrote the pair in.
  // A host that does not canonicalise (empty, or an unparseable URL) binds
  // nothing: there is no host to compare against and no host to sign.
  const bound = normalizeEmbedHost(matched.host);
  if (!bound) return null;

  // A host may appear at most once in the list. A host listed twice is
  // ambiguous, so the route refuses to mint for that host.
  const hostEntries = entries.filter(
    (entry) => normalizeEmbedHost(entry.host) === bound,
  );
  if (hostEntries.length !== 1) return null;

  return bound;
}

/**
 * True when the requested host is the host the credential is bound to.
 *
 * Both sides go through the house canonicaliser, so the route compares the
 * same thing the chat route compares when it verifies the proof. A host that
 * does not canonicalise matches nothing.
 */
export function tenantMintHostMatches(
  requestedHost: string,
  boundHost: string,
): boolean {
  const requested = normalizeEmbedHost(requestedHost);
  const bound = normalizeEmbedHost(boundHost);
  if (!requested || !bound) return false;
  return requested === bound;
}
