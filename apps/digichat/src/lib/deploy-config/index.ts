export {
  parseDigichatConfig,
  DigichatConfigSchema,
  DeploymentSchema,
  ChromeModeSchema,
  ThreadSkinSchema,
  PersistenceSchema,
  AuthModeSchema,
  DisclosureModeSchema,
  ViewModeSchema,
  ThinkingModeSchema,
  PageContextModeSchema,
  disclosureIsVisible,
  disclosureDefaultOpen,
  disclosureIsLocked,
  parseWelcomeCopy,
  welcomeTitle,
  welcomeBodyLines,
  allowlistModelId,
  type WelcomeCopy,
  type DigichatConfig,
  type DigichatDeployment,
  type ChromeMode,
  type ThreadSkin,
  type PersistenceMode,
  type AuthMode,
  type DisclosureMode,
  type UserAlign,
  type PageContextMode,
  type ToolCatalogEntry,
} from "./schema";

export {
  VIEW_MODES,
  THINKING_MODES,
  DEFAULT_VIEW_MODE,
  DEFAULT_THINKING_MODE,
  isViewMode,
  isThinkingMode,
  effectiveReasoningMode,
  effectiveToolCallsMode,
  type ViewMode,
  type ThinkingMode,
  type ChainDisclosureMode,
} from "@/lib/view-modes";

export {
  toDigichatClientConfig,
  toChromeClientConfig,
  DEFAULT_CLIENT_CONFIG,
  type DigichatClientConfig,
  type DigichatChromeClientConfig,
  type DigichatClientFeatures,
  type DigichatClientChrome,
  type DigichatClientModels,
} from "./client-projection";

/** Server-only loader lives in `./loader` — do not re-export here (node:fs). */

export {
  filterForceToolHeader,
  filterDisabledToolsHeader,
  catalogAllowsForceTool,
  catalogAllowsDisableId,
  allowedForceTools,
  omitForcedCatalogIds,
  FORCE_TOOL_BY_CATALOG_ID,
  DISABLEABLE_CATALOG_IDS,
} from "./force-tool";

export {
  isAllowedMcpServerUrl,
  resolveMcpOAuthResourceUrl,
  mcpServersHeaderValue,
  operatorMcpServersForUpstream,
  parseMcpSessionOverlay,
  mergeMcpSessionOverlay,
  mcpUpstreamHeaderValue,
} from "./mcp-servers";

export {
  clientConfigFromEmbedTenant,
  clientConfigFromDeployment,
} from "./embed-bridge";
