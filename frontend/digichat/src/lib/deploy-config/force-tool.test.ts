import { describe, expect, it } from "vitest";
import { DEFAULT_CLIENT_CONFIG } from "./client-projection";
import {
  filterDisabledToolsHeader,
  filterForceToolHeader,
  omitForcedCatalogIds,
} from "./force-tool";
import type { DigichatDeployment } from "./schema";

const dep = {
  slug: "embed",
  tools: {
    allowUserToggle: true,
    catalog: [
      { id: "digisearch", default: true },
      { id: "digivault", default: true },
      { id: "web_search", default: true },
    ],
  },
} as DigichatDeployment;

describe("filterDisabledToolsHeader", () => {
  it("allowlists catalog search/vault and drops unknown tokens", () => {
    expect(filterDisabledToolsHeader(dep, "digisearch,digivault,web_search,rm -rf")).toEqual([
      "digisearch",
      "digivault",
    ]);
  });

  it("maps aliases and ignores empty input", () => {
    expect(filterDisabledToolsHeader(dep, "search, vault")).toEqual(["digisearch", "digivault"]);
    expect(filterDisabledToolsHeader(dep, "")).toEqual([]);
    expect(filterDisabledToolsHeader(null, "digisearch")).toEqual(["digisearch"]);
    expect(filterDisabledToolsHeader(null, "rm -rf")).toEqual([]);
  });
});

describe("filterForceToolHeader", () => {
  it("forwards catalog force-tools only", () => {
    expect(filterForceToolHeader(dep, "digisearch")).toBe("digisearch");
    expect(filterForceToolHeader(dep, "digivault")).toBe("digivault");
    expect(filterForceToolHeader(dep, "not-a-tool")).toBeUndefined();
  });
});

describe("omitForcedCatalogIds", () => {
  it("keeps a forced catalog id out of the disabled list", () => {
    expect(omitForcedCatalogIds(["digisearch", "digivault"], "digisearch")).toEqual([
      "digivault",
    ]);
  });
});

void DEFAULT_CLIENT_CONFIG;
