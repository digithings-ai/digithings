"use client";

import { docsAssistantConfig } from "./assistant-config";
import { defaultBrandTheme, defaultDocsHostUi } from "./host-ui";
import type { BrandTheme, DocsAssistantConfig, DocsHostUiSpec } from "./types";
import { useSkinChrome } from "@/components/stock/skin-chrome";
import {
  createContext,
  useContext,
  useMemo,
  type CSSProperties,
  type ReactNode,
} from "react";

const defaultDocsConfig: {
  hostUi: DocsHostUiSpec;
  assistant: DocsAssistantConfig;
  brandTheme: BrandTheme;
} = {
  hostUi: defaultDocsHostUi,
  assistant: docsAssistantConfig,
  brandTheme: defaultBrandTheme,
};

const DocsConfigContext = createContext(defaultDocsConfig);

export function DocsConfigProvider({ children }: { children: ReactNode }) {
  const chrome = useSkinChrome();
  const config = useMemo(() => {
    const title = chrome.title?.trim();
    const welcome = chrome.welcome?.trim();
    const placeholder = chrome.placeholder?.trim();
    const hostUi = title
      ? {
          ...defaultDocsHostUi,
          root: {
            ...defaultDocsHostUi.root,
            props: {
              ...defaultDocsHostUi.root.props,
              productName: title,
            },
          },
        }
      : defaultDocsHostUi;
    const brandTheme = chrome.accent
      ? { ...defaultBrandTheme, accent: chrome.accent.color }
      : defaultBrandTheme;
    const assistant = {
      ...docsAssistantConfig,
      ...(title ? { productName: title, assistantName: title } : {}),
      welcome: {
        ...docsAssistantConfig.welcome,
        ...(welcome ? { headline: welcome } : {}),
      },
      labels: {
        ...docsAssistantConfig.labels,
        ...(placeholder
          ? { composerPlaceholder: placeholder }
          : {}),
      },
    };
    return { hostUi, assistant, brandTheme };
  }, [chrome]);

  const theme = config.brandTheme;
  const accentForeground = bestContrast(theme.accent);
  const style = {
    "--docs-accent": theme.accent,
    "--docs-accent-foreground": accentForeground,
    "--docs-accent-soft": colorMix(theme.accent, theme.surface, 0.12),
    "--docs-accent-softer": colorMix(theme.accent, theme.surface, 0.06),
    "--docs-surface": theme.surface,
    "--docs-border": theme.border,
    "--docs-muted": theme.mutedText,
    "--docs-ring": theme.focusRing,
    "--primary": theme.accent,
    "--primary-foreground": accentForeground,
    "--ring": theme.focusRing,
    "--accent": colorMix(theme.accent, theme.surface, 0.12),
    "--accent-foreground": accentForeground,
    "--border": theme.border,
    "--muted-foreground": theme.mutedText,
    "--sidebar-primary": theme.accent,
    "--sidebar-primary-foreground": accentForeground,
    "--sidebar-accent": colorMix(theme.accent, theme.surface, 0.12),
    "--sidebar-accent-foreground": accentForeground,
    "--sidebar-border": theme.border,
    "--sidebar-ring": theme.focusRing,
  } as CSSProperties;

  return (
    <DocsConfigContext.Provider value={config}>
      <div className="h-full" style={style}>
        {children}
      </div>
    </DocsConfigContext.Provider>
  );
}

export function useDocsConfig() {
  return useContext(DocsConfigContext);
}

function colorMix(first: string, second: string, firstWeight: number) {
  const a = parseHex(first);
  const b = parseHex(second);
  if (!a || !b) return first;

  const mix = a.map((value, index) =>
    Math.round(value * firstWeight + b[index] * (1 - firstWeight)),
  );
  return `#${mix.map((value) => value.toString(16).padStart(2, "0")).join("")}`;
}

function bestContrast(hex: string) {
  const rgb = parseHex(hex);
  if (!rgb) return "#ffffff";
  const luminance =
    (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
  return luminance > 0.6 ? "#0f172a" : "#ffffff";
}

function parseHex(hex: string) {
  const match = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!match) return null;
  const value = match[1];
  return [
    Number.parseInt(value.slice(0, 2), 16),
    Number.parseInt(value.slice(2, 4), 16),
    Number.parseInt(value.slice(4, 6), 16),
  ];
}
