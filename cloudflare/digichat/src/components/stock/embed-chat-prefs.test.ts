import { describe, expect, it } from "vitest";
import {
  extraOffFromCatalog,
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
