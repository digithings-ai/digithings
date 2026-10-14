import { describe, expect, it } from "vitest";
import {
  DEFAULT_SETTINGS,
  chatRequestBody,
  parseSettings,
  refreshIntervalMs,
  serializeSettings,
  staleBanner,
} from "./app-settings";

const SENTINEL = "sk-test-sentinel-not-a-real-key";

describe("app settings", () => {
  it("round-trips a valid document and drops anything that is not a setting", () => {
    const saved = serializeSettings({
      ...DEFAULT_SETTINGS,
      theme: "light",
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
      theme: "light",
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

  it("puts the allowed model on a chat send and the tab key only on that request", () => {
    const body = chatRequestBody("hello", DEFAULT_SETTINGS, SENTINEL);
    expect(body.model).toBe(DEFAULT_SETTINGS.chatModel);
    expect(body.byokKey).toBe(SENTINEL);
    expect(serializeSettings(DEFAULT_SETTINGS)).not.toContain(SENTINEL);
    const rejected = chatRequestBody("hello", { ...DEFAULT_SETTINGS, chatModel: "nope" }, "");
    expect(rejected.model).toBe(DEFAULT_SETTINGS.chatModel);
    expect(rejected.byokKey).toBeUndefined();
  });

  it("turns a refresh choice into a timer and a stale notice into a banner", () => {
    expect(refreshIntervalMs(0)).toBeNull();
    expect(refreshIntervalMs(15)).toBe(15_000);
    expect(staleBanner("stale", "stale")).toBe("This read is past the stale threshold.");
    expect(staleBanner("fresh", "stale")).toBeNull();
    expect(staleBanner("stale", "off")).toBeNull();
  });
});
