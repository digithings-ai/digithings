"use client";

import { useMemo } from "react";
import { Base } from "@/components/assistant-ui/skins/base/thread";
import { BaseConfigProvider } from "./config-provider";
import { defaultBaseConfig, type ResolvedBaseConfig } from "./defaults";
import { useSkinChrome } from "@/components/stock/skin-chrome";

/** Configurable Base catalog entry — official Base Thread + brandTheme shell. */
export function ConfigurableBase() {
  const chrome = useSkinChrome();
  const value = useMemo<ResolvedBaseConfig>(
    () => ({
      ...defaultBaseConfig,
      brandTheme: {
        ...defaultBaseConfig.brandTheme,
        ...(chrome.accent ? { accent: chrome.accent.color } : {}),
      },
      assistant: {
        ...defaultBaseConfig.assistant,
        appName: chrome.title?.trim() || defaultBaseConfig.assistant.appName,
        welcome: {
          headline:
            chrome.welcome?.trim() ||
            defaultBaseConfig.assistant.welcome.headline,
          body: defaultBaseConfig.assistant.welcome.body,
        },
        labels: {
          ...defaultBaseConfig.assistant.labels,
          composerPlaceholder:
            chrome.placeholder?.trim() ||
            defaultBaseConfig.assistant.labels.composerPlaceholder,
        },
      },
    }),
    [chrome],
  );

  return (
    <BaseConfigProvider value={value}>
      <Base />
    </BaseConfigProvider>
  );
}
