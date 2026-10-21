import { describe, it, expect, afterEach, vi } from "vitest";
import {
  THEME_MESSAGE_TYPE,
  MAX_THEME_AGE_MS,
  parseEmbedThemeParam,
  buildThemeMessage,
  parseThemeMessage,
  applyEmbedDocumentTheme,
  applyEmbedPalette,
  embedThemeColor,
  embedThemePick,
  embedUserThemeKey,
  resolveEmbedTheme,
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

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keys the pick by tenant slug so tenants on one origin never share it", () => {
    expect(embedUserThemeKey("occ")).toBe("dc-embed-theme:occ");
    const store = memoryStore();
    writeEmbedUserTheme(embedUserThemeKey("a"), { mode: "light", palette: "aura" }, store);
    expect(readEmbedUserTheme(embedUserThemeKey("a"), store)).toEqual({
      mode: "light",
      palette: "aura",
    });
    expect(readEmbedUserTheme(embedUserThemeKey("b"), store)).toBeNull();
  });

  it("writes the pick to sessionStorage, never to localStorage", () => {
    const session = memoryStore();
    const local = memoryStore();
    vi.stubGlobal("sessionStorage", session);
    vi.stubGlobal("localStorage", local);
    const key = embedUserThemeKey("a");
    writeEmbedUserTheme(key, { mode: "light", palette: "aura" });
    expect(session.map.get(key)).toBe(JSON.stringify({ mode: "light", palette: "aura" }));
    expect(local.map.size).toBe(0);
    expect(readEmbedUserTheme(key)).toEqual({ mode: "light", palette: "aura" });
  });

  it("keeps the pick in memory when sessionStorage is blocked", () => {
    vi.stubGlobal("sessionStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    });
    const key = embedUserThemeKey("blocked");
    writeEmbedUserTheme(key, { mode: "dark", palette: "dracula" });
    expect(readEmbedUserTheme(key)).toEqual({ mode: "dark", palette: "dracula" });
    writeEmbedUserTheme(key, null);
    expect(readEmbedUserTheme(key)).toBeNull();
  });

  it("keeps the pick in memory when sessionStorage reads work but writes throw", () => {
    const reads = memoryStore();
    vi.stubGlobal("sessionStorage", {
      getItem: reads.getItem,
      setItem: () => {
        throw new Error("QuotaExceededError");
      },
      removeItem: reads.removeItem,
    });
    const key = embedUserThemeKey("quota");
    writeEmbedUserTheme(key, { mode: "light", palette: "aura" });
    expect(readEmbedUserTheme(key)).toEqual({ mode: "light", palette: "aura" });
  });

  it("falls back to memory when a write fails after the probe passed", () => {
    const backing = memoryStore();
    let failWrites = false;
    vi.stubGlobal("sessionStorage", {
      getItem: backing.getItem,
      setItem: (k: string, v: string) => {
        if (failWrites && !k.endsWith("-probe")) throw new Error("QuotaExceededError");
        backing.setItem(k, v);
      },
      removeItem: backing.removeItem,
    });
    const key = embedUserThemeKey("late-quota");
    expect(readEmbedUserTheme(key)).toBeNull();
    failWrites = true;
    writeEmbedUserTheme(key, { mode: "dark", palette: "dracula" });
    expect(readEmbedUserTheme(key)).toEqual({ mode: "dark", palette: "dracula" });
  });

  it("a tenant slugged probe keeps its pick: the probe key is not a pick key", () => {
    const backing = memoryStore();
    vi.stubGlobal("sessionStorage", backing);
    const key = embedUserThemeKey("probe");
    backing.setItem(key, JSON.stringify({ mode: "light", palette: "aura" }));
    expect(readEmbedUserTheme(key)).toEqual({ mode: "light", palette: "aura" });
    expect(readEmbedUserTheme(key)).toEqual({ mode: "light", palette: "aura" });
    expect(backing.getItem(key)).not.toBeNull();
  });

  it("clears the pick, and ignores a malformed one", () => {
    const store = memoryStore();
    const key = embedUserThemeKey("a");
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

  it("maps /theme auto to no pick, and a mode to a pick that keeps the palette", () => {
    expect(embedThemePick("auto", "aura")).toBeNull();
    expect(embedThemePick("light", "aura")).toEqual({ mode: "light", palette: "aura" });
  });

  it("paints pick > parent > ?theme= > tenant, default dark", () => {
    const pick = { mode: "light" as const, palette: "default" as const };
    expect(resolveEmbedTheme({ pick, parent: "dark", url: "dark", tenant: "dark" })).toBe("light");
    expect(resolveEmbedTheme({ pick: null, parent: "light", url: "dark", tenant: "dark" })).toBe(
      "light",
    );
    expect(resolveEmbedTheme({ pick: null, parent: null, url: "light", tenant: "dark" })).toBe(
      "light",
    );
    expect(resolveEmbedTheme({ pick: null, parent: null, url: null, tenant: "light" })).toBe(
      "light",
    );
    expect(resolveEmbedTheme({ pick: null, parent: null, url: null, tenant: undefined })).toBe(
      "dark",
    );
    // Dropping the pick (/theme auto) returns to the tenant theme.
    expect(
      resolveEmbedTheme({
        pick: embedThemePick("auto", "aura"),
        parent: null,
        url: null,
        tenant: "light",
      }),
    ).toBe("light");
  });

  it("paints the palette and keeps theme-color in step", () => {
    const attrs = new Map<string, string>();
    const meta = new Map<string, string>();
    const doc = {
      documentElement: {
        setAttribute: (k: string, v: string) => void attrs.set(k, v),
        removeAttribute: (k: string) => void attrs.delete(k),
      },
      querySelector: (sel: string) =>
        sel === 'meta[name="theme-color"]'
          ? { setAttribute: (k: string, v: string) => void meta.set(k, v) }
          : null,
    } as unknown as Document;
    applyEmbedPalette("aura", "light", doc);
    expect(attrs.get("data-palette")).toBe("aura");
    expect(meta.get("content")).toBe(embedThemeColor("light", "aura"));
    expect(meta.get("content")).not.toBe("#f1f0eb");
    applyEmbedPalette("default", "dark", doc);
    expect(attrs.has("data-palette")).toBe(false);
    expect(meta.get("content")).toBe("#121417");
  });
});
