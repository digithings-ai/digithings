/**
 * Shared digichat version resolver.
 *
 * Imported by both `GET /api/health` and the license heartbeat sender so the
 * two surfaces cannot drift. Resolution order: `DIGICHAT_VERSION` env (baked
 * into the image from `package.json` at build time — see
 * `Dockerfile.digichat-cloudflare`) → `apps/digichat/package.json` version.
 */

import { version as packageVersion } from "../../../package.json";

export function resolveDigichatVersion(): string {
  return process.env.DIGICHAT_VERSION?.trim() || packageVersion;
}
