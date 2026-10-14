"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import {
  DEFAULT_SETTINGS,
  applyDocumentPrefs,
  parseSettings,
  refreshIntervalMs,
  serializeSettings,
  type AppSettings,
} from "./app-settings";

const KEY = "dq.app-settings";

const listeners = new Set<() => void>();
const keyListeners = new Set<() => void>();

let current: AppSettings = DEFAULT_SETTINGS;
let hydrated = false;
let sessionKey = "";

function emit(): void {
  for (const listener of listeners) listener();
}

function emitKey(): void {
  for (const listener of keyListeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function subscribeKey(listener: () => void): () => void {
  keyListeners.add(listener);
  return () => keyListeners.delete(listener);
}

/** Saved preferences. The first client render matches the server defaults, then storage loads. */
export function readSettings(): AppSettings {
  return hydrated ? current : DEFAULT_SETTINGS;
}

export function writeSettings(next: AppSettings): void {
  current = parseSettings(serializeSettings(next));
  hydrated = true;
  try {
    window.localStorage.setItem(KEY, serializeSettings(current));
  } catch {
    // Private mode: the in-memory copy still drives this tab.
  }
  emit();
}

export function readSessionKey(): string {
  return sessionKey;
}

/** Tab memory only. Never written next to the saved preferences. */
export function writeSessionKey(key: string): void {
  sessionKey = key;
  emitKey();
}

export function hydrateSettings(): void {
  if (typeof window === "undefined") return;
  try {
    current = parseSettings(window.localStorage.getItem(KEY));
    if (!current.defaultDesk) {
      const legacy = window.localStorage.getItem("dq-desk")?.trim() ?? "";
      if (legacy) {
        current = { ...current, defaultDesk: legacy };
        window.localStorage.setItem(KEY, serializeSettings(current));
      }
    }
  } catch {
    current = DEFAULT_SETTINGS;
  }
  hydrated = true;
  emit();
}

export function useAppSettings(): AppSettings {
  return useSyncExternalStore(subscribe, readSettings, () => DEFAULT_SETTINGS);
}

export function useSessionKey(): string {
  return useSyncExternalStore(subscribeKey, readSessionKey, () => "");
}

/** Bumps when the saved refresh interval elapses. Zero means the user left refresh off. */
export function useRefreshGeneration(): number {
  const settings = useAppSettings();
  const [generation, setGeneration] = useState(0);
  useEffect(() => {
    const ms = refreshIntervalMs(settings.refreshSec);
    if (ms === null) return;
    const id = window.setInterval(() => setGeneration((value) => value + 1), ms);
    return () => window.clearInterval(id);
  }, [settings.refreshSec]);
  return generation;
}

/** Applies theme and density on the document, and loads the saved document once. */
export function SettingsEffects() {
  const settings = useAppSettings();
  useEffect(() => {
    hydrateSettings();
  }, []);
  useEffect(() => {
    applyDocumentPrefs(settings, document.documentElement);
  }, [settings]);
  return null;
}
