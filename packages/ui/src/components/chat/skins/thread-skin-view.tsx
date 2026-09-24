"use client";

import { lazy, Suspense, type FC, type LazyExoticComponent } from "react";
import type { ComposerLayout } from "@digithings/ui/chat/thread";
import { isCloneSkin, type CloneSkin, type ThreadSkin } from "./thread-skins";
import type { DigichatSkinOptions } from "./digichat";

// Per-skin on-demand chunks (WS4 Step 5): each skin ships only when its id is
// selected. The `.then` interop maps the named export to the default that
// lazy() expects. Imports of types only (above) are erased, so they pull no
// chunk; the DigichatSkin *value* must stay out of the barrel for the same
// reason (hosts render it exclusively through ThreadSkinView).
const Base = lazy(() =>
  import("./base/thread").then((m) => ({ default: m.Base })),
);
const ChatGPT = lazy(() =>
  import("./chatgpt").then((m) => ({ default: m.ChatGPT })),
);
const Claude = lazy(() =>
  import("./claude").then((m) => ({ default: m.Claude })),
);
const Grok = lazy(() =>
  import("./grok").then((m) => ({ default: m.Grok })),
);
const Gemini = lazy(() =>
  import("./gemini").then((m) => ({ default: m.Gemini })),
);
const Perplexity = lazy(() =>
  import("./perplexity").then((m) => ({ default: m.Perplexity })),
);
const ReactInkWeb = lazy(() =>
  import("./react-ink").then((m) => ({ default: m.ReactInkWeb })),
);
const ExpoReactNative = lazy(() =>
  import("./expo-react-native").then((m) => ({ default: m.ExpoReactNative })),
);
const ConfigurableBase = lazy(() =>
  import("./base-assistant-ui").then((m) => ({ default: m.ConfigurableBase })),
);
const WebpageAssistant = lazy(() =>
  import("./webpage-assistant").then((m) => ({ default: m.WebpageAssistant })),
);
const ProductPageAssistant = lazy(() =>
  import("./product-page-assistant").then((m) => ({
    default: m.ProductPageAssistant,
  })),
);
const DigichatSkin = lazy(() =>
  import("./digichat").then((m) => ({ default: m.DigichatSkin })),
);

const CLONE_THREADS: Record<CloneSkin, LazyExoticComponent<FC>> = {
  chatgpt: ChatGPT,
  claude: Claude,
  grok: Grok,
  gemini: Gemini,
  perplexity: Perplexity,
};

export type ThreadSkinViewProps = {
  skin: ThreadSkin;
  /** Explicit composer layout for the digichat skin (else mode-derived). */
  composerLayout?: ComposerLayout;
  /**
   * First-party skin wiring (product copy, slash commands, pending headers).
   * Provided by the host app — e.g. digichat's `DIGICHAT_SKIN_OPTIONS`.
   * Only the `digichat` branch reads it; all other skins ignore it (WS4).
   */
  digichat?: DigichatSkinOptions;
};

/**
 * Mount the selected Thread: 11 official assistant-ui catalog ids, plus
 * first-party `digichat`. `base` is the fixed Base demo. `base-assistant-ui`
 * is the same Thread inside the official brandTheme / labels config shell.
 * Layout templates wrap a Thread in docs / product chrome.
 * `react-ink` and `expo-react-native` are web facsimiles; TTY / Expo sources
 * stay under `reference/assistant-ui-templates/` and are not imported here.
 */
export function ThreadSkinView(props: ThreadSkinViewProps) {
  // Suspense boundary for the per-skin chunks above. Fallback is null so no
  // loading chrome flashes when a newly selected skin's chunk arrives late;
  // once loaded the render is identical to the static version (WS4 Step 5).
  return (
    <Suspense fallback={null}>
      <ThreadSkinSwitch {...props} />
    </Suspense>
  );
}

function ThreadSkinSwitch({
  skin,
  composerLayout,
  digichat,
}: ThreadSkinViewProps) {
  if (isCloneSkin(skin)) {
    const Clone = CLONE_THREADS[skin];
    return <Clone />;
  }

  if (skin === "base") {
    return <Base />;
  }

  if (skin === "base-assistant-ui") {
    return <ConfigurableBase />;
  }

  if (skin === "react-ink") {
    return <ReactInkWeb />;
  }

  if (skin === "expo-react-native") {
    return <ExpoReactNative />;
  }

  if (skin === "webpage-assistant") {
    return <WebpageAssistant />;
  }

  if (skin === "digichat") {
    return <DigichatSkin composerLayout={composerLayout} {...digichat} />;
  }

  return <ProductPageAssistant />;
}

// Registry + host contract ship with the skins so any host can list skin ids
// and satisfy the mount requirements without importing the app (WS4).
export * from "./thread-skins";
export * from "./thread-skin-host-contract";
