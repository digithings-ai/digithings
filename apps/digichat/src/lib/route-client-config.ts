/**
 * Unified route client-config resolution (single-route plan, Step 2).
 *
 * The three routes used to assemble their configs three different ways:
 * product projected the deploy config, embed merged the verified tenant with
 * URL overrides, baseline inlined a narrow literal from the default config.
 * All three now go through this module.
 *
 * Pure + client-safe by construction: everything arrives as inputs. Callers
 * keep their own header/FS/env IO (deploy reads, tenant verification), so
 * this file bundles safely into client components too.
 */

import {
  clientConfigFromDeployment,
  clientConfigFromEmbedTenant,
  DEFAULT_CLIENT_CONFIG,
} from "./deploy-config";
import type { DigichatDeployment } from "./deploy-config/schema";
import type { EmbedTenantClientConfig } from "./embed-client-config";
import type { DigichatClientConfig } from "./deploy-config";
import type { StockChatPrefsConfig } from "@digithings/ui/chat/stock";
import { isEmbedHexColor } from "./embed-accent-style";
import { parseEmbedThemeParam } from "./embed-theme-messages";

/**
 * One call per route: product projects the primary deployment, embed
 * projects the verified tenant, catalog resolves the default config.
 */
export function resolveRouteClientConfig(
  input:
    | { mode: "product"; deployment: DigichatDeployment | null | undefined }
    | { mode: "embed"; tenant: EmbedTenantClientConfig }
    | { mode: "catalog" },
): DigichatClientConfig {
  switch (input.mode) {
    case "product":
      return clientConfigFromDeployment(input.deployment ?? null);
    case "embed":
      return clientConfigFromEmbedTenant(input.tenant);
    case "catalog":
      return DEFAULT_CLIENT_CONFIG;
  }
}

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/**
 * Embed seeded-tenant merge, moved verbatim from app/(digichat)/embed/page.
 *
 * The host's URL overrides (theme / welcome / placeholder / suggestions /
 * accent) seed the first paint too: the client hook applies them post-mount,
 * which would otherwise let the generic default copy ("Ask a question") and
 * other unconfigured values flash before the configured ones landed. Never
 * show a placeholder that is not configured.
 */
export function resolveEmbedSeededTenant(
  tenant: EmbedTenantClientConfig,
  params: Record<string, string | string[] | undefined>,
): {
  seeded: EmbedTenantClientConfig;
  urlTheme: ReturnType<typeof parseEmbedThemeParam>;
} {
  const urlTheme = parseEmbedThemeParam(first(params.theme));
  const uiWelcome = first(params.welcome);
  const uiPlaceholder = first(params.placeholder);
  const rawSuggestions = first(params.suggestions);
  const uiSuggestions = rawSuggestions
    ? (() => {
        try {
          const parsed = JSON.parse(rawSuggestions) as unknown;
          if (Array.isArray(parsed)) {
            return parsed.filter(
              (s): s is string => typeof s === "string" && s.trim().length > 0,
            );
          }
        } catch {
          /* fall through to the pipe-separated form */
        }
        return rawSuggestions
          .split("|")
          .map((s) => s.trim())
          .filter(Boolean);
      })()
    : undefined;
  const uiAccent = isEmbedHexColor(first(params.accent))
    ? first(params.accent)
    : undefined;
  const uiAccentForeground = isEmbedHexColor(first(params.accentForeground))
    ? first(params.accentForeground)
    : undefined;
  const themedCfg =
    urlTheme && urlTheme !== tenant.theme
      ? { ...tenant, theme: urlTheme }
      : tenant;
  const seededCfg = {
    ...themedCfg,
    ...(uiWelcome ? { welcome: uiWelcome } : {}),
    ...(uiPlaceholder ? { placeholder: uiPlaceholder } : {}),
    ...(uiSuggestions && uiSuggestions.length
      ? { suggestions: uiSuggestions }
      : {}),
    ...(uiAccent && uiAccentForeground
      ? { accent: { color: uiAccent, foreground: uiAccentForeground } }
      : {}),
  };
  return { seeded: seededCfg, urlTheme };
}

/**
 * Narrow prefs config shared by the two StockChatPrefsHost call sites
 * (home-stock-client Single/Memory and baseline-client). Previously two
 * identical 12-field literals; one function now.
 */
export function toStockChatPrefsConfig(
  clientConfig: DigichatClientConfig,
): StockChatPrefsConfig {
  return {
    catalog: clientConfig.tools.catalog,
    servers: clientConfig.mcp.servers,
    defaultLanguage: clientConfig.chrome.defaultLanguage,
    defaultModel: clientConfig.models.default,
    availableModels: clientConfig.models.available,
    allowModelPicker:
      clientConfig.models.allowPicker === true ||
      clientConfig.features.modelPicker === true,
    view: clientConfig.features.view,
    thinking: clientConfig.features.thinking,
    tenantAllowsWeb: clientConfig.gate.webSearch === true,
    showByok: clientConfig.gate.showByok === true,
    allowUserServers: clientConfig.mcp.allowUserServers,
    allowAddForm: clientConfig.mcp.allowAddForm,
  };
}
