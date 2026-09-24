/**
 * Skin registry + host contract + ThreadSkinView dispatch (WS4). The 12
 * skins live here; hosts mount them via ThreadSkinView and provide
 * first-party wiring through the `digichat` prop (see DigichatSkinOptions).
 */
export { ThreadSkinView, type ThreadSkinViewProps } from "./thread-skin-view";
export {
  DigichatSkin,
  type DigichatSkinCopy,
  type DigichatSkinOptions,
  type DigichatSkinSlash,
  type SkinSlashAction,
  type SkinSlashAdapterLike,
  type SkinSlashCommand,
  type SkinSlashExtraDef,
} from "./digichat";
export {
  CLONE_SKINS,
  DEFAULT_THREAD_SKIN,
  FIRST_PARTY_DEFAULT_SKIN_HOSTS,
  FIRST_PARTY_DEFAULT_SKIN_SLUGS,
  FRAMED_CHROME_MODES,
  LAYOUT_SKINS,
  THREAD_SKINS,
  defaultThreadSkinForTenant,
  isCloneSkin,
  isFramedPresentation,
  isThreadSkin,
  parseThreadSkin,
  skinCreditStyle,
  skinOwnsPageChrome,
  threadSkinChoices,
  type CloneSkin,
  type FramedChromeMode,
  type LayoutSkin,
  type ThreadSkin,
} from "./thread-skins";
export {
  DIGICHAT_SKIN_HOST_CONTRACT,
  type SkinHostContract,
} from "./thread-skin-host-contract";
