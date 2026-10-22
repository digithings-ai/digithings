/**
 * Skin-support primitives (WS4): catalog primitives, prefs shell, skin
 * chrome, Thread and tool UI. Hosts import ThreadSkinView from
 * `@digithings/ui/chat/skins` and the prefs host from here.
 */

export {
  DEFAULT_DEPLOY_UI,
  DeployUiProvider,
  useDeployUi,
  useDisclosureUi,
  type DeployUiValue,
} from "./deploy-ui-context";
export {
  DEFAULT_SKIN_CHROME,
  SkinChromeProvider,
  useAttribution,
  useComposerCopy,
  useSkinChrome,
  type SkinChromeValue,
} from "./skin-chrome";
export {
  StockSendGateProvider,
  useStockComposerGateSubmit,
  useStockSendGate,
  type StockSendGateHandlers,
} from "./stock-send-gate";
// The prefs twin of the view ids. Hosts keep their own id contract
// (`apps/digichat/src/lib/view-modes.ts`) and this normaliser is the other
// half of it, so a host can check that both name the same levels instead of
// trusting that they do. The alias map is exported under a name of its own:
// it is the twin's map to compare against the host's, not the host's.
export {
  LEGACY_VIEW_MODE_ALIASES as PREFS_LEGACY_VIEW_MODE_ALIASES,
  normalizeViewPref,
  type ChainDisclosureMode,
  type ChromeMode,
  type PageContextMode,
  type UserAlign,
  type ViewMode,
  isStockComposerMenuKind,
  type StockComposerMenuKind,
} from "./skin-types";
export {
  SkinRuntime,
  SkinRuntimeProvider,
  useSkinRuntime,
  type ParsedSkinError,
  type SkinErrorParsers,
  type SkinRuntimeValue,
} from "./skin-runtime";
// WS4: catalog primitives + prefs shell moved from the app. Hosts import
// ThreadSkinView from `@digithings/ui/chat/skins` and the prefs host from here.
export { MessageError } from "./message-error.aui";
export {
  EmbedChatPrefsProvider,
  useEmbedChatPrefs,
  useEmbedChatPrefsOptional,
  DEFAULT_EMBED_CHAT_PREFS,
  createDefaultEmbedChatPrefs,
  chromePrefsFromDeploy,
  persistDensity,
  useStoredDensityAfterMount,
  disabledCatalogIds,
  catalogToolsFromClient,
  extraOffFromCatalog,
  type EmbedChatPrefs,
  type EmbedChatPrefsApi,
  type CatalogToolRow,
} from "./embed-chat-prefs";
export {
  useStockChatPrefs,
  StockChatPrefsHost,
  type StockChatPrefsConfig,
  type StockChatPrefsDeps,
} from "./stock-chat-prefs-host";
// DIG-2882: the session artifact panel and the artifact `a:` override.
export {
  ArtifactsPanel,
  ArtifactLink,
  artifactListPath,
  artifactBlobPath,
  isArtifactBlobHref,
  formatArtifactSize,
  formatArtifactDate,
  type ArtifactRow,
  type ArtifactIo,
} from "./artifacts-panel";
export { SkinCredit, SKIN_CREDIT_TEXT } from "./skin-credit";
export { Thread } from "./thread.aui";
export {
  ToolFallback,
  ToolFallbackArgs,
  ToolFallbackAttribution,
  ToolFallbackContent,
  ToolFallbackResult,
  ToolFallbackRoot,
  ToolFallbackTrigger,
  formatToolDuration,
  type ToolFallbackRootProps,
} from "./tool-fallback.aui";
export { toolRowTitle } from "./tool-display";
