"use client";

import type { FC } from "react";
import type { ComposerLayout } from "@digithings/web/chat/thread";
import { Base } from "@/components/assistant-ui/skins/base/thread";
import {
  isCloneSkin,
  type CloneSkin,
  type ThreadSkin,
} from "@/lib/thread-skins";
import { ChatGPT } from "./chatgpt";
import { Claude } from "./claude";
import { Grok } from "./grok";
import { Gemini } from "./gemini";
import { Perplexity } from "./perplexity";
import { ReactInkWeb } from "./react-ink";
import { ExpoReactNative } from "./expo-react-native";
import { ConfigurableBase } from "./base-assistant-ui";
import { WebpageAssistant } from "./webpage-assistant";
import { ProductPageAssistant } from "./product-page-assistant";
import { DigichatSkin } from "./digichat";

const CLONE_THREADS: Record<CloneSkin, FC> = {
  chatgpt: ChatGPT,
  claude: Claude,
  grok: Grok,
  gemini: Gemini,
  perplexity: Perplexity,
};

export type ThreadSkinViewProps = {
  skin: ThreadSkin;
  /** Welcome headline — unused on official clones / layouts (they keep demo copy). */
  welcome?: string;
  /** Explicit composer layout for the digichat skin (else mode-derived). */
  composerLayout?: ComposerLayout;
};

/**
 * Mount the selected Thread: 11 official assistant-ui catalog ids, plus
 * first-party `digichat`. `base` is the fixed Base demo. `base-assistant-ui`
 * is the same Thread inside the official brandTheme / labels config shell.
 * Layout templates wrap a Thread in docs / product chrome.
 * `react-ink` and `expo-react-native` are web facsimiles; TTY / Expo sources
 * stay under `reference/assistant-ui-templates/` and are not imported here.
 */
export function ThreadSkinView({ skin, composerLayout }: ThreadSkinViewProps) {
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
    return <DigichatSkin composerLayout={composerLayout} />;
  }

  return <ProductPageAssistant />;
}
