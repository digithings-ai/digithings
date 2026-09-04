import { describe, it, expect } from "vitest";
import { resolveAttributionPlacement, resolveEmbedUiFlags } from "./embed-ui-flags";

describe("resolveEmbedUiFlags", () => {
  it("keeps showByok true under ungated", () => {
    expect(
      resolveEmbedUiFlags({
        slug: "digithings",
        gateMode: "ungated",
        theme: "dark",
        accent: null,
        attribution: false,
        showByok: true,
        layout: "page",
      }),
    ).toEqual({
      showByok: true,
      layout: "page",
      showLanguageSelector: false,
      webSearch: false,
    });
  });

  it("does not derive showByok from gateMode", () => {
    expect(
      resolveEmbedUiFlags({
        slug: "x",
        gateMode: "turn_limited",
        theme: "dark",
        accent: null,
        attribution: false,
      }),
    ).toEqual({
      showByok: false,
      layout: "embed",
      showLanguageSelector: false,
      webSearch: false,
    });
  });

  it("passes webSearch through only when true (#3420)", () => {
    expect(
      resolveEmbedUiFlags({
        slug: "x",
        gateMode: "ungated",
        theme: "dark",
        accent: null,
        attribution: false,
        webSearch: true,
      }).webSearch,
    ).toBe(true);
  });

  it("resolveEmbedUiFlags passes showLanguageSelector through", () => {
    expect(
      resolveEmbedUiFlags({
        slug: "x",
        gateMode: "ungated",
        theme: "dark",
        accent: null,
        attribution: false,
        showLanguageSelector: true,
      }).showLanguageSelector,
    ).toBe(true);
    expect(
      resolveEmbedUiFlags({
        slug: "x",
        gateMode: "ungated",
        theme: "dark",
        accent: null,
        attribution: false,
        showLanguageSelector: false,
      }).showLanguageSelector,
    ).toBe(false);
  });
});

// The credit renders in at most one place. It used to be gated `attribution &&
// !headerTitle`, so a titled tenant could never get the footer at all and was
// stuck with the header parenthetical beside its own name — a co-brand, not a
// credit. Turning `attribution` on now MOVES it rather than adding a second.
describe("resolveAttributionPlacement", () => {
  it("puts the credit in the footer when the tenant opted in", () => {
    expect(resolveAttributionPlacement({ attribution: true, headerTitle: "DataTap" })).toBe(
      "footer",
    );
  });

  it("still prefers the footer for an untitled opted-in embed", () => {
    expect(resolveAttributionPlacement({ attribution: true, headerTitle: null })).toBe("footer");
  });

  it("leaves an opted-out titled tenant on the header parenthetical", () => {
    expect(resolveAttributionPlacement({ attribution: false, headerTitle: "DataTap" })).toBe(
      "header",
    );
  });

  it("shows nothing when an opted-out embed has no title of its own", () => {
    // The header is already the digichat wordmark — "digichat (by digichat)".
    expect(resolveAttributionPlacement({ attribution: false, headerTitle: null })).toBe("none");
    expect(resolveAttributionPlacement({ attribution: false })).toBe("none");
  });

  it("never asks for both at once", () => {
    for (const attribution of [true, false]) {
      for (const headerTitle of ["DataTap", null, ""]) {
        const at = resolveAttributionPlacement({ attribution, headerTitle });
        expect(["footer", "header", "none"]).toContain(at);
      }
    }
  });
});
