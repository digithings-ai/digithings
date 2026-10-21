/**
 * Server-side replay of a stored conversation. Branding comes from the
 * deployment that is loaded now; theme, palette, and view can be overridden
 * so a demo agent can match the screen it just recorded.
 */

import type { DigichatDeployment } from "@/lib/deploy-config/schema";
import { welcomeBodyLines, welcomeTitle } from "@/lib/deploy-config/schema";
import type { ReplayChromeInput, ReplayView } from "@digithings/ui/replay";

const VIEWS = new Set<ReplayView>(["quiet", "balanced", "verbose"]);

export function replayChromeForDeployment(
  deployment: DigichatDeployment | null,
  tenantSlug: string,
  url: URL,
): ReplayChromeInput {
  const themeParam = url.searchParams.get("theme");
  const resolved = themeParam === "light" || themeParam === "dark" ? themeParam : deploymentTheme(deployment);
  const paletteParam = url.searchParams.get("palette")?.trim().toLowerCase() ?? "";
  const palette =
    paletteParam === "default" || /^[a-z0-9-]+$/.test(paletteParam) ? paletteParam || "default" : "default";
  const viewParam = url.searchParams.get("view");
  const view = VIEWS.has(viewParam as ReplayView) ? (viewParam as ReplayView) : deploymentView(deployment);
  const chrome = deployment?.chrome;
  return {
    deployment: deployment?.slug || tenantSlug || "digichat",
    title: chrome?.title,
    welcome: welcomeTitle(chrome?.welcome) ?? "",
    welcomeBody: welcomeBodyLines(chrome?.welcome),
    suggestions: chrome?.suggestions ?? [],
    placeholder: chrome?.placeholder,
    accent: chrome?.accent ?? null,
    theme: {
      preference: resolved,
      resolved,
      palette,
      view,
    },
  };
}

export function replayExportedAt(url: URL, now = new Date()): string {
  const raw = url.searchParams.get("at");
  if (!raw) return now.toISOString();
  const when = new Date(raw);
  return Number.isNaN(when.getTime()) ? now.toISOString() : when.toISOString();
}

function deploymentTheme(deployment: DigichatDeployment | null): "light" | "dark" {
  return deployment?.chrome.theme === "light" ? "light" : "dark";
}

function deploymentView(deployment: DigichatDeployment | null): ReplayView {
  const view = deployment?.features.view;
  return VIEWS.has(view as ReplayView) ? (view as ReplayView) : "balanced";
}
