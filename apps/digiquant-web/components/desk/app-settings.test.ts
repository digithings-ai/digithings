import { describe, expect, it } from "vitest";
import {
  DEFAULT_SETTINGS,
  chatRequestBody,
  clearDocumentPrefs,
  applyDocumentPrefs,
  parseSettings,
  refreshIntervalMs,
  serializeSettings,
  staleBanner,
  THEMES,
} from "./app-settings";

const SENTINEL = "sk-test-sentinel-not-a-real-key";

describe("app settings", () => {
  it("round-trips a valid document and drops anything that is not a setting", () => {
    const saved = serializeSettings({
      ...DEFAULT_SETTINGS,
      density: "compact",
      refreshSec: 30,
      staleSessions: 1,
      notify: "stale",
      chatModel: DEFAULT_SETTINGS.chatModel,
      defaultDesk: "core",
    });
    expect(saved).not.toContain(SENTINEL);
    expect(saved).not.toContain("byok");
    expect(parseSettings(saved)).toMatchObject({
      theme: "dark",
      density: "compact",
      refreshSec: 30,
      staleSessions: 1,
      notify: "stale",
      defaultDesk: "core",
    });
  });

  it("rejects a model outside the allowlist and a theme that is not offered", () => {
    const raw = JSON.stringify({
      theme: "neon",
      chatModel: "not-a-listed-model",
      refreshSec: 7,
      staleSessions: 9,
      apiKey: SENTINEL,
    });
    const settings = parseSettings(raw);
    expect(settings.theme).toBe("dark");
    expect(settings.chatModel).toBe(DEFAULT_SETTINGS.chatModel);
    expect(settings.refreshSec).toBe(0);
    expect(settings.staleSessions).toBe(3);
    expect(serializeSettings(settings)).not.toContain(SENTINEL);
  });

  it("drops a stored light theme: the desk has no light scheme", () => {
    expect(THEMES).toEqual(["dark"]);
    expect(parseSettings(JSON.stringify({ theme: "light" })).theme).toBe("dark");
  });

  it("puts only the text and an allowed model on a chat send", () => {
    expect(chatRequestBody("hello", DEFAULT_SETTINGS)).toEqual({ text: "hello", model: DEFAULT_SETTINGS.chatModel });
    expect(chatRequestBody("hello", { ...DEFAULT_SETTINGS, chatModel: "nope" }).model).toBe(DEFAULT_SETTINGS.chatModel);
  });

  it("sets density and leaves the document theme alone", () => {
    const attrs = new Map<string, string>([["data-theme", "light"]]);
    const root = {
      setAttribute: (name: string, value: string) => void attrs.set(name, value),
      removeAttribute: (name: string) => void attrs.delete(name),
    };
    applyDocumentPrefs({ ...DEFAULT_SETTINGS, density: "compact" }, root);
    expect(attrs.get("data-theme")).toBe("light");
    expect(attrs.get("data-density")).toBe("compact");
    clearDocumentPrefs(root);
    expect(attrs.get("data-theme")).toBe("light");
    expect(attrs.has("data-density")).toBe(false);
  });

  it("turns a refresh choice into a timer and a stale notice into a banner", () => {
    expect(refreshIntervalMs(0)).toBeNull();
    expect(refreshIntervalMs(15)).toBe(15_000);
    expect(staleBanner("stale", "stale")).toBe("This read is past the stale threshold.");
    expect(staleBanner("fresh", "stale")).toBeNull();
    expect(staleBanner("stale", "off")).toBeNull();
  });
});
