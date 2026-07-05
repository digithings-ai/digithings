"use client";

import { useEffect, useState } from "react";
import { p } from "@/lib/base-path";
import { resolveEmbedHost } from "@/lib/embed-gate";

export type EmbedTenantClientConfig = {
  slug: string;
  gateMode: "turn_limited" | "ungated";
  theme: "dark" | "light";
  accent: { color: string; foreground: string } | null;
  attribution: boolean;
};

/** Legacy defaults — deliberately the *gated* configuration, so a slow or
 * failed config fetch can only be more restrictive than intended, never less. */
export const DEFAULT_EMBED_TENANT_CONFIG: EmbedTenantClientConfig = {
  slug: "embed",
  gateMode: "turn_limited",
  theme: "dark",
  accent: null,
  attribution: false,
};

/**
 * @param token - Per-tenant secret from the embed snippet's own `?token=`
 * param (see embed-tenants.ts). Without it, the server can't tell this caller
 * apart from anyone else claiming the same (public) host, and returns the
 * generic gated defaults instead of this tenant's config (#1339).
 */
export function useEmbedTenantConfig(token?: string | null): EmbedTenantClientConfig {
  const [config, setConfig] = useState<EmbedTenantClientConfig>(DEFAULT_EMBED_TENANT_CONFIG);

  useEffect(() => {
    let cancelled = false;
    const headers: Record<string, string> = { "X-Embed-Host": resolveEmbedHost() };
    if (token) headers["X-Embed-Token"] = token;
    fetch(p("/api/embed/tenant-config"), { headers })
      .then((r) => (r.ok ? r.json() : null))
      .then((json: EmbedTenantClientConfig | null) => {
        if (
          !cancelled &&
          json &&
          (json.gateMode === "turn_limited" || json.gateMode === "ungated")
        ) {
          setConfig(json);
        }
      })
      .catch(() => {
        /* keep gated defaults */
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return config;
}
