// Plain node environment (no DOM) -- `import.meta.url` under the happy-dom
// pragma resolves to a non-file:// URL, so source-text checks live in their
// own file rather than ContactMailto.shared.test.tsx.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

describe("embed paywall contact", () => {
  it("keeps the locked-contact card on the shared ContactMailto, off raw mailto: anchors (#2226)", () => {
    // PaywallCard's lockedContact branch (embed-client.tsx) used to render
    // <a href={`mailto:${lockedContact}`}>{lockedContact}</a> directly -- the
    // most severe pattern (bare address as visible link text), on the same
    // digithings.ai/occ.digithings.ai zone confirmed to have Cloudflare Email
    // Address Obfuscation on (#2220). It must stay on the shared component.
    const path = fileURLToPath(new URL("../app/embed/embed-client.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");
    expect(src).not.toContain("mailto:");
    expect(src).toContain("<ContactMailto");
    expect(src).toContain('from "@digithings/web"');
  });
});
