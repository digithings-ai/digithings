import { describe, expect, it } from "vitest";
import { DEFAULT_EMBED_CHAT_PREFS, disabledCatalogIds } from "./embed-chat-prefs";

describe("disabledCatalogIds", () => {
  it("is empty when search and vault are on", () => {
    expect(disabledCatalogIds(DEFAULT_EMBED_CHAT_PREFS)).toEqual([]);
  });

  it("lists catalog ids that are off", () => {
    expect(
      disabledCatalogIds({
        ...DEFAULT_EMBED_CHAT_PREFS,
        digisearch: false,
        vault: false,
      }),
    ).toEqual(["digisearch", "digivault"]);
  });
});
