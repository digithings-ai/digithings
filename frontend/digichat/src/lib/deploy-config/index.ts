export {
  parseDigichatConfig,
  DigichatConfigSchema,
  DeploymentSchema,
  ChromeModeSchema,
  ThreadSkinSchema,
  PersistenceSchema,
  AuthModeSchema,
  DisclosureModeSchema,
  disclosureIsVisible,
  disclosureDefaultOpen,
  disclosureIsLocked,
  parseWelcomeCopy,
  welcomeTitle,
  welcomeBodyLines,
  type WelcomeCopy,
  type DigichatConfig,
  type DigichatDeployment,
  type ChromeMode,
  type ThreadSkin,
  type PersistenceMode,
  type AuthMode,
  type DisclosureMode,
  type UserAlign,
  type ToolCatalogEntry,
} from "./schema";

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
  catalogAllowsForceTool,
  allowedForceTools,
  FORCE_TOOL_BY_CATALOG_ID,
} from "./force-tool";

export {
  clientConfigFromEmbedTenant,
  clientConfigFromDeployment,
} from "./embed-bridge";
