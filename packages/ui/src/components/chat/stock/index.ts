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
