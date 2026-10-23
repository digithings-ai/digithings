import { describe, expect, it, vi } from "vitest";
import {
  extraOffFromCatalog,
  createDefaultEmbedChatPrefs,
  chromePrefsFromDeploy,
  resetChromePrefsFromDeploy,
  DEFAULT_EMBED_CHAT_PREFS,
  disabledCatalogIds,
} from "./embed-chat-prefs";

describe("disabledCatalogIds", () => {
  it("defaults web search on; the tenant gate still decides whether it sends", () => {
    expect(DEFAULT_EMBED_CHAT_PREFS.webSearch).toBe(true);
  });

  it("is empty when search and vault are on", () => {
    expect(disabledCatalogIds(DEFAULT_EMBED_CHAT_PREFS)).toEqual([]);
  });

  it("starts extra MCP tools off when YAML default is false", () => {
    expect(extraOffFromCatalog([{ id: "datatap", default: false }])).toEqual({
      datatap: false,
    });
    expect(extraOffFromCatalog([{ id: "datatap", default: true }])).toEqual({});
    expect(extraOffFromCatalog([{ id: "datatap" }])).toEqual({});
  });

  it("lists catalog ids that are off", () => {
    expect(
      disabledCatalogIds({
        ...DEFAULT_EMBED_CHAT_PREFS,
        digisearch: false,
        vault: false,
        extra: { datatap: false },
      }),
    ).toEqual(["digisearch", "digivault", "datatap"]);
  });
});

describe("searchEngine pref", () => {
  it("defaults to unset (follow-tenant) rather than a literal engine", () => {
    expect(DEFAULT_EMBED_CHAT_PREFS.searchEngine).toBe("");
    expect(createDefaultEmbedChatPrefs().searchEngine).toBe("");
  });
});

describe("composer chrome prefs", () => {
  it("shows the composer footer row by default", () => {
    expect(DEFAULT_EMBED_CHAT_PREFS.toolbar).toBe(true);
    expect(createDefaultEmbedChatPrefs().toolbar).toBe(true);
  });

  it("keeps scrollbars always visible by default", () => {
    expect(DEFAULT_EMBED_CHAT_PREFS.scrollbars).toBe("always");
    expect(createDefaultEmbedChatPrefs().scrollbars).toBe("always");
  });

  it("starts on the default worked-chain rhythm", () => {
    expect(DEFAULT_EMBED_CHAT_PREFS.density).toBe("default");
    expect(createDefaultEmbedChatPrefs().density).toBe("default");
  });

  it("starts following the stream", () => {
    expect(DEFAULT_EMBED_CHAT_PREFS.scroll).toBe("follow");
    expect(createDefaultEmbedChatPrefs().scroll).toBe("follow");
  });
});

describe("chromePrefsFromDeploy", () => {
  it("lets a stored density win over the deployment, and ignores an unknown stored value", () => {
    const stored = {
      getItem: (key: string) => (key === "dt-density" ? "airy" : null),
    };
    expect(chromePrefsFromDeploy({ density: "compact" }, stored).density).toBe("airy");
    expect(
      chromePrefsFromDeploy({ density: "compact" }, { getItem: () => "roomy" }).density,
    ).toBe("compact");
    expect(chromePrefsFromDeploy({ density: "nope" }, null).density).toBe("default");
  });

  it("lets a stored scroll choice win over the deployment", () => {
    const stored = {
      getItem: (key: string) => (key === "dt-scroll" ? "free" : null),
    };
    expect(chromePrefsFromDeploy({ scroll: "follow" }, stored).scroll).toBe("free");
    expect(chromePrefsFromDeploy({ scroll: "free" }, null).scroll).toBe("free");
    expect(
      chromePrefsFromDeploy({ scroll: "free" }, { getItem: () => "wide" }).scroll,
    ).toBe("free");
    expect(chromePrefsFromDeploy({}, null).scroll).toBe("follow");
  });

  it("seeds the other palette settings from the deployment and keeps today's defaults", () => {    expect(chromePrefsFromDeploy({}, null)).toMatchObject({
      effort: "medium",
      searchEngine: "",
      toolbar: true,
      scrollbars: "always",
    });
    expect(
      chromePrefsFromDeploy(
        { effort: "high", searchEngine: "exa", toolbar: false, scrollbars: "auto" },
        null,
      ),
    ).toMatchObject({
      effort: "high",
      searchEngine: "exa",
      toolbar: false,
      scrollbars: "auto",
    });
  });
});

describe("resetChromePrefsFromDeploy", () => {
  function withEnv(mobile: boolean, stored: string | null, run: () => void): void {
    vi.stubGlobal("window", {
      matchMedia: (query: string) => ({
        matches: mobile && query === "(max-width: 640px)",
      }),
    });
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => (key === "dt-density" ? stored : null),
      setItem: () => {},
      removeItem: () => {},
    });
    try {
      run();
    } finally {
      vi.unstubAllGlobals();
    }
  }

  it("keeps the phone default on a reset instead of dropping to the deployment", () => {
    withEnv(true, null, () => {
      expect(resetChromePrefsFromDeploy({ density: "compact" }).density).toBe("airy");
    });
  });

  it("still lets a stored choice win on a phone", () => {
    withEnv(true, "compact", () => {
      expect(resetChromePrefsFromDeploy({ density: "airy" }).density).toBe("compact");
    });
  });

  it("uses the deployment density on a desktop", () => {
    withEnv(false, null, () => {
      expect(resetChromePrefsFromDeploy({ density: "compact" }).density).toBe("compact");
    });
  });
});
