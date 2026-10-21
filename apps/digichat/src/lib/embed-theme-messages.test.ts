import { describe, it, expect, afterEach, vi } from "vitest";
import {
  THEME_MESSAGE_TYPE,
  MAX_THEME_AGE_MS,
  parseEmbedThemeParam,
  buildThemeMessage,
  parseThemeMessage,
  applyEmbedDocumentTheme,
  applyEmbedPalette,
  embedUserThemeKey,
  readEmbedUserTheme,
  writeEmbedUserTheme,
} from "./embed-theme-messages";

describe("embed-theme-messages", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("exports digichat:theme", () => {
    expect(THEME_MESSAGE_TYPE).toBe("digichat:theme");
    expect(buildThemeMessage("light").type).toBe("digichat:theme");
  });

  describe("parseEmbedThemeParam", () => {
    it("accepts light and dark only", () => {
      expect(parseEmbedThemeParam("light")).toBe("light");
      expect(parseEmbedThemeParam("dark")).toBe("dark");
      expect(parseEmbedThemeParam("midnight")).toBeNull();
      expect(parseEmbedThemeParam(undefined)).toBeNull();
      expect(parseEmbedThemeParam(null)).toBeNull();
      expect(parseEmbedThemeParam("")).toBeNull();
    });
  });

  describe("parseThemeMessage", () => {
    const allowed = new Set(["https://digithings.ai"]);

    it("accepts a well-formed theme from digithings.ai", () => {
      const event = {
        origin: "https://digithings.ai",
        data: buildThemeMessage("light"),
      } as MessageEvent;
      expect(parseThemeMessage(event, allowed)?.theme).toBe("light");
    });

    it("ignores wrong origin", () => {
      const event = {
        origin: "https://evil.example",
        data: buildThemeMessage("dark"),
      } as MessageEvent;
      expect(parseThemeMessage(event, allowed)).toBeNull();
    });

    it("rejects invalid theme values", () => {
      const event = {
        origin: "https://digithings.ai",
        data: { type: THEME_MESSAGE_TYPE, theme: "auto", ts: Date.now() },
      } as MessageEvent;
      expect(parseThemeMessage(event, allowed)).toBeNull();
    });

    it("rejects missing or stale ts", () => {
      const noTs = {
        origin: "https://digithings.ai",
        data: { type: THEME_MESSAGE_TYPE, theme: "light" },
      } as MessageEvent;
      expect(parseThemeMessage(noTs, allowed)).toBeNull();

      vi.useFakeTimers();
      vi.setSystemTime(new Date("2026-08-10T12:00:00Z"));
      const stale = {
        origin: "https://digithings.ai",
        data: buildThemeMessage("dark", Date.now() - MAX_THEME_AGE_MS - 1),
      } as MessageEvent;
      expect(parseThemeMessage(stale, allowed)).toBeNull();
    });
  });

  describe("applyEmbedDocumentTheme", () => {
    it("sets data-theme and mirrors .light/.dark classes", () => {
      const classes = new Set<string>();
      let dataTheme = "";
      const el = {
        setAttribute(name: string, value: string) {
          if (name === "data-theme") dataTheme = value;
        },
        classList: {
          add(...tokens: string[]) {
            for (const t of tokens) classes.add(t);
          },
          remove(...tokens: string[]) {
            for (const t of tokens) classes.delete(t);
          },
        },
      };

      applyEmbedDocumentTheme("light", el);
      expect(dataTheme).toBe("light");
      expect(classes.has("light")).toBe(true);
      expect(classes.has("dark")).toBe(false);

      applyEmbedDocumentTheme("dark", el);
      expect(dataTheme).toBe("dark");
      expect(classes.has("dark")).toBe(true);
      expect(classes.has("light")).toBe(false);
    });
  });
});

describe("embed /theme pick (2.6.6)", () => {
  function memoryStore() {
    const map = new Map<string, string>();
    return {
      map,
      getItem: (k: string) => map.get(k) ?? null,
      setItem: (k: string, v: string) => void map.set(k, v),
      removeItem: (k: string) => void map.delete(k),
    };
  }

  it("keys the pick by embed host so tenants on one origin never share it", () => {
    expect(embedUserThemeKey("occ.digithings.ai")).toBe("dc-embed-theme:occ.digithings.ai");
    expect(embedUserThemeKey(undefined)).toBe("dc-embed-theme:default");
    const store = memoryStore();
    writeEmbedUserTheme(embedUserThemeKey("a.example"), { mode: "light", palette: "aura" }, store);
    expect(readEmbedUserTheme(embedUserThemeKey("a.example"), store)).toEqual({
      mode: "light",
      palette: "aura",
    });
    expect(readEmbedUserTheme(embedUserThemeKey("b.example"), store)).toBeNull();
  });

  it("clears the pick, and ignores a malformed one", () => {
    const store = memoryStore();
    const key = embedUserThemeKey("a.example");
    writeEmbedUserTheme(key, { mode: "dark", palette: "default" }, store);
    writeEmbedUserTheme(key, null, store);
    expect(store.map.size).toBe(0);
    store.setItem(key, "{not json");
    expect(readEmbedUserTheme(key, store)).toBeNull();
    store.setItem(key, JSON.stringify({ mode: "sepia", palette: "aura" }));
    expect(readEmbedUserTheme(key, store)).toBeNull();
    store.setItem(key, JSON.stringify({ mode: "dark", palette: "nope" }));
    expect(readEmbedUserTheme(key, store)).toEqual({ mode: "dark", palette: "default" });
  });

  it("paints the pick's palette and removes it for the default", () => {
    const attrs = new Map<string, string>();
    const el = {
      setAttribute: (k: string, v: string) => void attrs.set(k, v),
      removeAttribute: (k: string) => void attrs.delete(k),
    };
    applyEmbedPalette("aura", el);
    expect(attrs.get("data-palette")).toBe("aura");
    applyEmbedPalette("default", el);
    expect(attrs.has("data-palette")).toBe(false);
  });
});
