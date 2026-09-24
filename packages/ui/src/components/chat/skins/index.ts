/**
 * Skin registry + host contract (WS4). ThreadSkinView and the 12 skins move
 * here in Step 4; the registry and contract move first so hosts can re-point.
 */
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
