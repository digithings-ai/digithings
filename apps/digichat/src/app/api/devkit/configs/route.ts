import { join } from "node:path";
import { isLocalBaselinePreview } from "@/lib/baseline-preview";
import { listDevkitEntries } from "@/lib/devkit-configs";

export const dynamic = "force-dynamic";

/**
 * Dev-only devkit surface (no `requireDigiChatAuth()` — same documented
 * exception as dev-only `POST /api/baseline-chat`): lists local deployment
 * configs with secret scalars redacted. 404 outside development loopback so
 * file contents and secret shapes cannot ship as a public API.
 */
export async function GET(req: Request) {
  if (!isLocalBaselinePreview(req)) {
    return new Response(null, { status: 404 });
  }
  const configDir = join(process.cwd(), "config");
  const entries = listDevkitEntries(configDir, process.env, process.cwd());
  return Response.json({ entries });
}
