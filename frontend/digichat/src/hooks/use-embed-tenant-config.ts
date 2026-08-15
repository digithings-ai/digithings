"use client";

import { useEffect, useState } from "react";
import { p } from "@/lib/base-path";
import { resolveEmbedHost } from "@/lib/embed-gate";
import {
  DEFAULT_EMBED_TENANT_CONFIG,
  type EmbedTenantClientConfig,
} from "@/lib/embed-client-config";

export {
  DEFAULT_EMBED_TENANT_CONFIG,
  type EmbedTenantClientConfig,
} from "@/lib/embed-client-config";

/**
 * @param token - Per-tenant secret from the embed snippet's own `?token=`
 * param (see embed-tenants.ts). Without it, the server can't tell this caller
 * apart from anyone else claiming the same (public) host, and returns the
 * generic gated defaults instead of this tenant's config (#1339).
 * @param explicitHost - see resolveEmbedHost(); the embedding page's own
 * origin, passed via the iframe src's `?host=` param (#1372).
 * @param initial - the SAME config already resolved server-side and rendered
 * into the first paint (see resolveEmbedClientConfigFromParams). Seeding state
 * with it is what removes the dark→tenant-theme flash: without it this hook
 * starts at the gated dark defaults and only reaches the tenant's theme once
 * the fetch below resolves, so every embed painted dark for one round-trip
 * regardless of the tenant's actual theme. The fetch still runs — it is the
 * live source of truth, and re-asserting it costs nothing when it agrees.
 */
export function useEmbedTenantConfig(
  token?: string | null,
  explicitHost?: string | null,
  initial: EmbedTenantClientConfig = DEFAULT_EMBED_TENANT_CONFIG,
): EmbedTenantClientConfig {
  const [config, setConfig] = useState<EmbedTenantClientConfig>(initial);

  useEffect(() => {
    let cancelled = false;
    const headers: Record<string, string> = { "X-Embed-Host": resolveEmbedHost(explicitHost) };
    if (token) headers["X-Embed-Token"] = token;
    fetch(p("/api/embed/tenant-config"), { headers })
      .then((r) => (r.ok ? r.json() : null))
      .then((json: EmbedTenantClientConfig | null) => {
        if (
          !cancelled &&
          json &&
          (json.gateMode === "turn_limited" ||
            json.gateMode === "ungated" ||
            json.gateMode === "trial_form")
        ) {
          setConfig(json);
        }
      })
      .catch(() => {
        /* keep whatever we already have — server-resolved, or gated defaults */
      });
    return () => {
      cancelled = true;
    };
  }, [token, explicitHost]);

  return config;
}
