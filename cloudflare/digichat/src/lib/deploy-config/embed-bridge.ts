/**
 * Bridge deploy client config ↔ legacy EmbedTenantClientConfig fields
 * so embed-client and tenant-config routes stay compatible while migrating.
 */

import type { EmbedTenantClientConfig } from "@/lib/embed-client-config";
import type { DigichatDeployment } from "./schema";
import {
  DEFAULT_CLIENT_CONFIG,
  toDigichatClientConfig,
  type DigichatClientConfig,
} from "./client-projection";
import { defaultThreadSkinForTenant } from "@/lib/thread-skins";

/** Merge legacy embed client fields into a DigichatClientConfig for ProductStockShell. */
export function clientConfigFromEmbedTenant(
  embed: EmbedTenantClientConfig,
  base: DigichatClientConfig = DEFAULT_CLIENT_CONFIG,
): DigichatClientConfig {
  const webSearch = embed.webSearch === true;
  const catalog = (embed.tools?.catalog ?? []).map((e) => ({
    id: e.id,
    // Omitted `default` means session-OFF (#3805 fail-closed for promote).
    // Only explicit `default: true` starts the tool on.
    default: e.default === true,
    ...(e.label ? { label: e.label } : {}),
  }));
  if (webSearch && !catalog.some((t) => t.id === "web_search")) {
    catalog.push({ id: "web_search", default: true, label: "Web search" });
  }

  return {
    ...base,
    slug: embed.slug || base.slug,
    chrome: {
      ...base.chrome,
      mode: embed.layout === "page" ? "app" : "embed",
      theme: embed.theme,
      skin: embed.skin ?? defaultThreadSkinForTenant({ slug: embed.slug }),
      title: embed.title,
      welcome: embed.welcome ?? base.chrome.welcome,
      welcomeBody: embed.welcomeBody ?? [],
      suggestions: embed.suggestions ?? base.chrome.suggestions,
      placeholder: embed.placeholder ?? base.chrome.placeholder,
      accent: embed.accent,
      attribution: embed.attribution,
    },
    persistence: "none",
    auth: "anonymous",
    features: {
      ...base.features,
      attachments: embed.attachments === true,
    },
    models: {
      ...(embed.models?.default ? { default: embed.models.default } : base.models),
      available: embed.models?.available ?? base.models.available,
      allowPicker:
        embed.models?.allowPicker === true ||
        (embed.models?.allowPicker !== false && base.features.modelPicker),
    },
    tools: {
      allowUserToggle: base.tools.allowUserToggle,
      catalog,
    },
    mcp: {
      servers: (embed.mcp?.servers ?? []).map((s) => ({
        id: s.id,
        ...(s.label ? { label: s.label } : {}),
        ...(typeof s.default === "boolean" ? { default: s.default } : {}),
      })),
      allowUserServers: embed.mcp?.allowUserServers === true,
      allowAddForm: embed.mcp?.allowUserServers === true && embed.mcp?.allowAddForm === true,
    },
    gate: {
      ...base.gate,
      mode: embed.gateMode,
      llmAccess: embed.llmAccess,
      lockedContact: embed.lockedContact,
      showByok: embed.showByok,
      showLanguageSelector: embed.showLanguageSelector,
      webSearch,
    },
    backendType: embed.backendType ?? base.backendType,
  };
}

export function clientConfigFromDeployment(
  dep: DigichatDeployment | null | undefined,
): DigichatClientConfig {
  if (!dep) return DEFAULT_CLIENT_CONFIG;
  return toDigichatClientConfig(dep);
}
