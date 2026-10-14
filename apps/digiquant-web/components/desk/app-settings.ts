import rawModels from "../../../digichat/config/digichat-deploy-models.json";

/**
 * Desk preferences the settings page can change.
 * A provider key never belongs in this document: it stays in tab memory.
 * Chat models are the digichat deploy allowlist, not a free string.
 */

type ModelTable = { default: string; available: string[] };

const models = rawModels as ModelTable;

if (!models.available.includes(models.default)) {
  throw new Error("digichat deploy models: the default is not in the allowlist");
}

export const CHAT_MODELS: readonly string[] = models.available;

export const THEMES = ["dark", "light"] as const;
export const DENSITIES = ["regular", "compact"] as const;
export const REFRESH_SECONDS = [0, 15, 30, 60, 120] as const;
export const STALE_SESSIONS = [1, 2, 3, 5] as const;
export const NOTIFY_MODES = ["off", "stale"] as const;

export type ThemeName = (typeof THEMES)[number];
export type DensityName = (typeof DENSITIES)[number];
export type RefreshSec = (typeof REFRESH_SECONDS)[number];
export type StaleSessions = (typeof STALE_SESSIONS)[number];
export type NotifyMode = (typeof NOTIFY_MODES)[number];

export type AppSettings = {
  defaultDesk: string | null;
  theme: ThemeName;
  density: DensityName;
  refreshSec: RefreshSec;
  staleSessions: StaleSessions;
  notify: NotifyMode;
  chatModel: string;
};

export const DEFAULT_SETTINGS: AppSettings = {
  defaultDesk: null,
  theme: "dark",
  density: "regular",
  refreshSec: 0,
  staleSessions: 3,
  notify: "off",
  chatModel: models.default,
};

export type ChatRequestBody = {
  text: string;
  model: string;
  byokKey?: string;
};

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === "string" && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

function oneNum<T extends number>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === "number" && (allowed as readonly number[]).includes(value) ? (value as T) : fallback;
}

export function allowedModel(id: string): string {
  return (CHAT_MODELS as readonly string[]).includes(id) ? id : DEFAULT_SETTINGS.chatModel;
}

export function normalizeSettings(input: Partial<AppSettings>): AppSettings {
  const desk = typeof input.defaultDesk === "string" ? input.defaultDesk.trim() : "";
  return {
    defaultDesk: desk.length > 0 ? desk : null,
    theme: oneOf(input.theme, THEMES, DEFAULT_SETTINGS.theme),
    density: oneOf(input.density, DENSITIES, DEFAULT_SETTINGS.density),
    refreshSec: oneNum(input.refreshSec, REFRESH_SECONDS, DEFAULT_SETTINGS.refreshSec),
    staleSessions: oneNum(input.staleSessions, STALE_SESSIONS, DEFAULT_SETTINGS.staleSessions),
    notify: oneOf(input.notify, NOTIFY_MODES, DEFAULT_SETTINGS.notify),
    chatModel: allowedModel(typeof input.chatModel === "string" ? input.chatModel : ""),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Read a stored document. Unknown fields, including any key, are ignored. */
export function parseSettings(raw: string | null): AppSettings {
  if (!raw) return DEFAULT_SETTINGS;
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value)) return DEFAULT_SETTINGS;
    return normalizeSettings({
      defaultDesk: typeof value.defaultDesk === "string" ? value.defaultDesk : null,
      theme: value.theme as ThemeName,
      density: value.density as DensityName,
      refreshSec: value.refreshSec as RefreshSec,
      staleSessions: value.staleSessions as StaleSessions,
      notify: value.notify as NotifyMode,
      chatModel: typeof value.chatModel === "string" ? value.chatModel : "",
    });
  } catch {
    return DEFAULT_SETTINGS;
  }
}

/** The document written to storage. It has no room for a provider key. */
export function serializeSettings(settings: AppSettings): string {
  return JSON.stringify(normalizeSettings(settings));
}

export function refreshIntervalMs(refreshSec: RefreshSec): number | null {
  return refreshSec > 0 ? refreshSec * 1000 : null;
}

export function staleBanner(state: "fresh" | "warn" | "stale" | null, notify: NotifyMode): string | null {
  if (notify !== "stale" || state !== "stale") return null;
  return "This read is past the stale threshold.";
}

/** The body of one chat send. The key is present only for this request. */
export function chatRequestBody(text: string, settings: AppSettings, sessionKey: string): ChatRequestBody {
  const body: ChatRequestBody = { text, model: allowedModel(settings.chatModel) };
  const key = sessionKey.trim();
  if (key) body.byokKey = key;
  return body;
}

export function applyDocumentPrefs(
  settings: AppSettings,
  root: { setAttribute(name: string, value: string): void },
): void {
  root.setAttribute("data-theme", settings.theme);
  root.setAttribute("data-density", settings.density);
}
