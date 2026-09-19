"use client";

import { defaultBrandTheme, supportAssistantConfig } from "@/lib/support/assistant-config";
import {
  createContext,
  useContext,
  type CSSProperties,
  type ReactNode,
} from "react";

const defaultSupportConfig = {
  assistant: supportAssistantConfig,
  brandTheme: defaultBrandTheme,
};

const SupportConfigContext = createContext(defaultSupportConfig);

export function SupportConfigProvider({ children }: { children: ReactNode }) {
  const theme = defaultSupportConfig.brandTheme;
  const accentForeground = bestContrast(theme.accent);
  const style = {
    "--support-accent": theme.accent,
    "--support-accent-foreground": accentForeground,
    "--support-accent-soft": colorMix(theme.accent, theme.surface, 0.12),
    "--support-accent-softer": colorMix(theme.accent, theme.surface, 0.06),
    "--support-border": theme.border,
    "--support-muted": theme.mutedText,
    "--support-success": theme.success,
    "--support-warning": theme.warning,
    "--support-destructive": theme.destructive,
    "--support-ring": theme.focusRing,
    "--primary": theme.accent,
    "--primary-foreground": accentForeground,
    "--ring": theme.focusRing,
    "--accent": colorMix(theme.accent, theme.surface, 0.12),
    "--accent-foreground": accentForeground,
    "--border": theme.border,
    "--muted-foreground": theme.mutedText,
  } as CSSProperties;

  return (
    <SupportConfigContext.Provider value={defaultSupportConfig}>
      <div className="h-full" style={style}>
        {children}
      </div>
    </SupportConfigContext.Provider>
  );
}

export function useSupportConfig() {
  return useContext(SupportConfigContext);
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
  return luminance > 0.6 ? "#111827" : "#ffffff";
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
