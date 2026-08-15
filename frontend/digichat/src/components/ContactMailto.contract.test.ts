// Plain node environment (no DOM) -- `import.meta.url` under the happy-dom
// pragma resolves to a non-file:// URL, so source-text checks live in their
// own file rather than ContactMailto.test.tsx.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

describe("ContactMailto contracts", () => {
  it("never returns a literal mailto: string or the email prop from its JSX (#2226)", () => {
    // Cloudflare's Email Address Obfuscation rewrites whatever the render
    // body actually returns, so that return statement must never contain
    // "mailto:" or reference `email` directly -- only the effect (which runs
    // after Cloudflare's edge has nothing left to rewrite) may assign the
    // real href/text.
    const path = fileURLToPath(new URL("./ContactMailto.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");
    const returnBlock = src.slice(src.indexOf("return ("), src.lastIndexOf(");"));
    expect(returnBlock).not.toContain("mailto:");
    expect(returnBlock).not.toContain("{email}");
    expect(returnBlock).toContain('href="#"');
  });

  it("keeps the embed's locked-contact paywall card off a raw mailto: anchor (#2226)", () => {
    // PaywallCard's lockedContact branch (embed-client.tsx) used to render
    // <a href={`mailto:${lockedContact}`}>{lockedContact}</a> directly -- the
    // most severe pattern (bare address as visible link text), on the same
    // digithings.ai/occ.digithings.ai zone already confirmed to have
    // Cloudflare Email Address Obfuscation on (#2220).
    const path = fileURLToPath(new URL("../app/embed/embed-client.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");
    expect(src).not.toContain("mailto:");
    expect(src).toContain("<ContactMailto");
  });
});
