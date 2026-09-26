/**
 * digichat fold (slice 3, #4689): route the standalone digichat worker's paths
 * through the digithings-stack worker to a third Container (Next standalone
 * on :3000).
 *
 * Same paths, one predicate: the branch in index.ts matches with
 * `shouldProxyToDigiChat` re-exported from the standalone worker's own
 * `apps/digichat-cloudflare/src/paths.ts` — nothing is reimplemented here, so
 * the folded paths stay identical to the standalone worker (`/embed*`,
 * `/api/chat*`, `/api/embed/*`, `/api/byok/*`, `/api/plan-proof*`,
 * `/api/health`, `/_dtchat/*`; Pages keeps owning `/chat` and marketing).
 *
 * Auth stays in-container: the stack worker applies no edge gating on
 * digichat paths (no 401, no JWT check) — the Next process enforces its own
 * embed-tenant auth exactly as on the standalone worker.
 *
 * Isolation: index.ts loads this module lazily through
 * `runIsolated("digichat", () => import("./digichat"), ...)` — a digichat
 * failure degrades only its own paths (503); every other group keeps
 * serving. The static `shouldProxyToDigiChat` import in index.ts is the same
 * pattern as ports.ts: this file is dependency-free (one re-export plus two
 * constants), so it cannot fail independently of the worker bundle.
 *
 * Secrets: the stack's `DigiChatContainer.envVars` (index.ts) mirrors the
 * standalone worker's container env 1:1 with the same `??` defaults. No
 * values ship in this slice — the standalone worker stays deployed until
 * cutover; secrets land via `wrangler secret put` later. No DNS/Pages/route
 * changes in this slice.
 */

export { shouldProxyToDigiChat } from "../../digichat-cloudflare/src/paths";
export { SHARED_DIGICHAT_CONTAINER_ID } from "../../digichat-cloudflare/src/paths";

/** Next standalone port inside the digichat Container (matches EXPOSE 3000 / PORT=3000). */
export const DIGICHAT_PORT = 3000;
