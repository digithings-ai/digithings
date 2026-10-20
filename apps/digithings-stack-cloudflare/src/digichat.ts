/**
 * digichat fold residue (slice 3, #4689; the fold was dropped 2026-10-19).
 *
 * The folded proxy branch was removed from index.ts when digichat (and OCC,
 * one of its tenants) moved back to its own Worker (`apps/digichat-cloudflare`
 * / `digithings-digichat`). Nothing in the stack Worker imports this module
 * for routing any more.
 *
 * It stays because it re-exports the standalone worker's own predicate and
 * container-id derivation — the same values, not copies — and
 * `src/digichat-mount.test.js` pins them against the standalone worker. That
 * test also pins the Next standalone port used by the image bind. The stack
 * Worker no longer has a digichat Container, so no `envVars` live here and this
 * module makes no `envVars` claim: the Container's runtime env is
 * `apps/digichat-cloudflare/src/index.ts`.
 */

export { shouldProxyToDigiChat } from "../../digichat-cloudflare/src/paths";
// DIG-3814: the Container id is DERIVED from the deploying commit by the
// standalone worker's own paths.ts, and the fold re-exports that function
// itself rather than keeping a second copy. That is what makes "folded id
// equals standalone id" true by construction instead of by two literals
// happening to match — a fold that reimplemented the derivation would drift
// the moment either side changed.
export { sharedDigichatContainerId, digichatContainerRev } from "../../digichat-cloudflare/src/paths";

/** Next standalone port inside the digichat Container (matches EXPOSE 3000 / PORT=3000). */
export const DIGICHAT_PORT = 3000;
