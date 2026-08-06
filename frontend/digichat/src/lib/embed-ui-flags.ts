import type { EmbedTenantClientConfig } from "@/hooks/use-embed-tenant-config";

export function resolveEmbedUiFlags(cfg: EmbedTenantClientConfig): {
  showByok: boolean;
  showStatusBar: boolean;
  layout: "page" | "embed";
} {
  return {
    showByok: cfg.showByok === true,
    showStatusBar: cfg.showStatusBar === true,
    layout: cfg.layout === "page" ? "page" : "embed",
  };
}
