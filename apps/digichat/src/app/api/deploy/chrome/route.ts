/**
 * Client-safe chrome projection for widget.js / dashboard popup.
 * Never includes tokens, MCP URLs, or backend credentials.
 *
 * GET /api/deploy/chrome?host=<hostname>
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

export const dynamic = "force-dynamic";

export async function GET(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const host = url.searchParams.get("host")?.trim() || undefined;

  let body;
  try {
    const cfg = getDigichatConfig();
    const dep = resolveDeploymentForHost(host, cfg) ?? getPrimaryDeployment(cfg);
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
