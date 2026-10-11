import { describe, expect, it } from "vitest";
import {
  DEVKIT_LOOKS,
  DEVKIT_MODES,
  devkitModeForChrome,
  groupEntriesByLook,
  lookForEntry,
  withChromeMode,
} from "./devkit-looks";

/** The nine shipped configs, as devkit-configs.ts labels them. */
const SHIPPED = [
  { id: "file:config/examples/local-app.yaml", slug: "local-app", chromeMode: "app" },
  { id: "file:config/examples/local-app-memory.yaml", slug: "local-app", chromeMode: "app" },
  { id: "file:config/examples/local-cli.yaml", slug: "local-cli", chromeMode: "app" },
  { id: "file:config/examples/occ-embed.yaml#hosts/occ", slug: "occ", chromeMode: "embed" },
  { id: "file:config/examples/digithings-ai-embed.yaml#hosts/digithings-ai", slug: "digithings-ai", chromeMode: "embed" },
  { id: "file:config/examples/dashboard-modal.yaml", slug: "digiquant-dashboard", chromeMode: "modal" },
  { id: "file:config/examples/datatap-mcp.yaml", slug: "datatap", chromeMode: "embed" },
  { id: "file:config/datatap-trial-foundry.yaml", slug: "datatap-trial-foundry", chromeMode: "embed" },
  { id: "file:config/datatap-trial-test.yaml", slug: "datatap-trial-test", chromeMode: "embed" },
] as const;

describe("look catalog", () => {
  it("names every look the brief asks for", () => {
    const ids = DEVKIT_LOOKS.map((l) => l.id);
    for (const wanted of ["client", "occ", "datatap", "digichat", "banner"]) {
      expect(ids).toContain(wanted);
    }
  });

  it("collapses the shipped configs into the named looks", () => {
    const groups = groupEntriesByLook(SHIPPED);
    const byId = Object.fromEntries(groups.map((g) => [g.id, g.variantIds]));
    expect(byId.datatap).toHaveLength(3);
    expect(byId.client).toHaveLength(2);
    expect(byId.banner).toHaveLength(1);
    expect(byId.occ).toHaveLength(1);
    expect(byId.digichat).toHaveLength(1);
  });

  it("LOSES NO CONFIG — every entry lands in exactly one look", () => {
    const total = groupEntriesByLook(SHIPPED).reduce(
      (n, g) => n + g.variantIds.length,
      0,
    );
    expect(total).toBe(SHIPPED.length);
    const flat = groupEntriesByLook(SHIPPED).flatMap((g) => g.variantIds);
    expect(new Set(flat).size).toBe(flat.length);
  });

  it("keeps a look the brief did not name rather than deleting it", () => {
    // local-cli is a shipped config and four distinct look; the brief does not
    // list it. Dropping it would make a shipped deployment unreachable.
    expect(lookForEntry(SHIPPED[2])).toBe("cli");
  });

  it("drops an empty look rather than rendering a header with no options", () => {
    // SHIPPED has no skins, so no `skins` group is emitted — an empty
    // SelectGroup would render a label with nothing under it.
    expect(groupEntriesByLook(SHIPPED).map((g) => g.id)).not.toContain("skins");
  });

  it("keeps the 12 thread-skin configs OUT of the default-client look", () => {
    // config/examples/skins/*.yaml ship 12 configs whose slugs are
    // `client-<skin>`; they are the skin catalogue, not a product look.
    for (const skin of ["base", "digichat", "gemini", "webpage-assistant"]) {
      expect(lookForEntry({ id: "s", slug: `client-${skin}`, chromeMode: "app" })).toBe("skins");
    }
    expect(
      groupEntriesByLook(SHIPPED).find((g) => g.id === "client")!.variantIds,
    ).not.toContain("file:skins.yaml");
  });

  it("classifies the pop-up banner by slug so the selector (no chrome access) agrees", () => {
    // The deployment selector only has id/label/ok; if the banner needed
    // chromeMode the two surfaces would disagree on the same file.
    expect(
      lookForEntry({ id: "x", slug: "digiquant-dashboard", chromeMode: undefined }),
    ).toBe("banner");
  });

  it("orders groups by the reviewer's order, not alphabetically", () => {
    expect(groupEntriesByLook(SHIPPED).map((g) => g.id)).toEqual([
      "client",
      "occ",
      "datatap",
      "digichat",
      "banner",
      "cli",
    ]);
  });
});

describe("preview modes", () => {
  it("maps the three named modes onto real chrome-schema values", () => {
    expect(DEVKIT_MODES.map((m) => [m.id, m.chromeMode])).toEqual([
      ["fullscreen", "app"],
      ["popup", "modal"],
      ["embedded", "embed"],
    ]);
  });

  it("seeds the selected mode from the deployment's own chrome.mode", () => {
    expect(devkitModeForChrome("modal")).toBe("popup");
    expect(devkitModeForChrome("app")).toBe("fullscreen");
    expect(devkitModeForChrome("embed")).toBe("embedded");
  });

  it("falls back to embedded for a mode the brief does not name", () => {
    // `sidebar` is a fourth schema value; the switcher must still render.
    expect(devkitModeForChrome("sidebar")).toBe("embedded");
    expect(devkitModeForChrome(undefined)).toBe("embedded");
  });

  it("re-projects chrome.mode without mutating or dirtying the draft", () => {
    const deployment = { slug: "x", chrome: { mode: "embed", theme: "dark" } };
    const next = withChromeMode(deployment as never, "modal");
    expect(next.chrome.mode).toBe("modal");
    expect(next.chrome.theme).toBe("dark");
    // Non-vacuity: the source object must be untouched, or the mode switch
    // would write back into the draft text the operator never edited.
    expect(deployment.chrome.mode).toBe("embed");
  });

  it("round-trips a mode change back to the original", () => {
    const deployment = { slug: "x", chrome: { mode: "embed", skin: "digichat" } };
    const there = withChromeMode(deployment as never, "app");
    const back = withChromeMode(there, "embed");
    expect(back).toEqual(deployment);
  });
});
