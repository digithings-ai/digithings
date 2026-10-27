/**
 * Client-safe chrome projection for widget.js / dashboard popup.
 * Never includes tokens, MCP URLs, or backend credentials.
 *
 * GET /api/deploy/chrome?host=<hostname>
 *
 * An invite-only host (DIG-3585) answers 404 unless the request carries that
 * deployment's own token in `X-Embed-Token`. The edge adds that header on the
 * invite page's own calls. The token is never read from the query string, so
 * it stays out of URLs and logs.
 */

import {
  toChromeClientConfig,
  DEFAULT_CLIENT_CONFIG,
} from "@/lib/deploy-config";
import {
  getDigichatConfig,
  resolveDeploymentForHost,
  getPrimaryDeployment,
} from "@/lib/deploy-config/loader";
import { tokenMatches } from "@/lib/embed-chat-tenant";
import { isInviteOnlyDeployment } from "@/lib/embed-invite-only";

export const dynamic = "force-dynamic";

function notFound(): Response {
  return new Response(JSON.stringify({ error: "not_found" }), {
    status: 404,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

export async function GET(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const host = url.searchParams.get("host")?.trim() || undefined;

  let body;
  try {
    const cfg = getDigichatConfig();
    const dep = resolveDeploymentForHost(host, cfg) ?? getPrimaryDeployment(cfg);
    if (
      isInviteOnlyDeployment(host, dep?.slug) &&
      !(dep && tokenMatches(dep.token ?? "", req.headers.get("x-embed-token")))
    ) {
      return notFound();
    }
    body = dep
      ? toChromeClientConfig(dep)
      : {
          slug: DEFAULT_CLIENT_CONFIG.slug,
          ...DEFAULT_CLIENT_CONFIG.chrome,
          persistence: DEFAULT_CLIENT_CONFIG.persistence,
          auth: DEFAULT_CLIENT_CONFIG.auth,
        };
  } catch {
    body = {
      slug: DEFAULT_CLIENT_CONFIG.slug,
      ...DEFAULT_CLIENT_CONFIG.chrome,
      persistence: DEFAULT_CLIENT_CONFIG.persistence,
      auth: DEFAULT_CLIENT_CONFIG.auth,
    };
  }

  return new Response(JSON.stringify(body), {
    status: 200,
    headers: {
      "content-type": "application/json",
      "cache-control": "no-store",
      // Allow parent pages (dashboard, marketing) to read chrome labels/hotkeys.
      "access-control-allow-origin": "*",
    },
  });
}
