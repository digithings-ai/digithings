/**
 * ContactMailto contracts — guards for the Cloudflare Email Address
 * Obfuscation workaround (#2220/#2226). The return block must never carry a
 * literal `mailto:` string or a bare address: the edge rewrites those in
 * served HTML, diverging from React's hydration payload. The real href/text
 * derive only after the hydration-safe client mount flag flips.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { buildMailtoHref, ContactMailto } from "./ContactMailto";

describe("ContactMailto contracts", () => {
  it("builds a plain mailto: href, with an optional subject query", () => {
    expect(buildMailtoHref("x@y.com")).toBe("mailto:x@y.com");
    expect(buildMailtoHref("x@y.com", "hello%20there")).toBe(
      "mailto:x@y.com?subject=hello%20there",
    );
  });

  it("exports the component", () => {
    expect(typeof ContactMailto).toBe("function");
  });

  it("never bakes a literal mailto: string or a bare address into server-rendered JSX", () => {
    const path = fileURLToPath(new URL("./ContactMailto.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");

    const returnBlock = src.slice(src.indexOf("return ("), src.lastIndexOf(");"));
    expect(returnBlock).not.toContain("mailto:");
    expect(returnBlock).not.toContain("@");
    expect(returnBlock).toContain("readyHref");

    // Outside the doc comment, the only literal "mailto:" in the file is the
    // template-string prefix inside buildMailtoHref — not duplicated inline
    // anywhere a server-rendered value (JSX, an href attribute) could carry it.
    const code = src.slice(src.indexOf("*/") + 2);
    expect(code.match(/mailto:/g)?.length).toBe(1);
  });

  it("always renders children, even for showAddress, so the link has visible text and an accessible name before mount", () => {
    // Suppressing children whenever showAddress is set would server-render
    // an empty, unlabeled link until JS runs. children always render;
    // showAddress only controls whether the mount path swaps in the address.
    const path = fileURLToPath(new URL("./ContactMailto.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");
    expect(src).not.toMatch(/showAddress\s*\?\s*null/);
    expect(src).toContain("{addressText ?? children}");
  });
});
