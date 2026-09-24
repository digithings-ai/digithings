/**
 * Skin-support primitives (WS4). Pure moves first; the NEEDS-INTERFACE modules
 * (skin-chrome, message-error, embed-chat-prefs, prefs-host) get their cuts in
 * Step 3. Skins + the rest of stock/ move here in Step 4.
 */
export { CreditFooter } from "./credit-footer";
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
export type {
  ChainDisclosureMode,
  ChromeMode,
  PageContextMode,
  UserAlign,
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
export { Thread } from "./thread.aui";
export {
  ToolFallback,
  ToolFallbackAttribution,
  formatToolDuration,
  type ToolFallbackRootProps,
} from "./tool-fallback.aui";
export { toolRowTitle } from "./tool-display";
