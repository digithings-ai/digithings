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

export function useEmbedTenantConfig(): EmbedTenantClientConfig {
  const [config, setConfig] = useState<EmbedTenantClientConfig>(DEFAULT_EMBED_TENANT_CONFIG);

  useEffect(() => {
    let cancelled = false;
    fetch(p("/api/embed/tenant-config"), {
      headers: { "X-Embed-Host": resolveEmbedHost() },
    })
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
  }, []);

  return config;
}
