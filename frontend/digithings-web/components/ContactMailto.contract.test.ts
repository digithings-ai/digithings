import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { buildMailtoHref, ContactMailto } from "@/components/ContactMailto";
import { DT_CONTACT_EMAIL } from "@/app/_nav";

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

  it("never bakes a literal mailto: string or the bare address into server-rendered JSX (#2220)", async () => {
    // Cloudflare's Email Address Obfuscation rewrites any literal mailto:
    // href, or bare email address text, present in the HTML it actually
    // serves -- diverging from what the origin (and therefore React's
    // hydration payload) produced, and throwing a hydration mismatch on
    // every page carrying a contact link. The real href/text must only ever
    // be assigned inside the client-only useEffect below, never returned
    // from the component's JSX.
    const path = fileURLToPath(new URL("./ContactMailto.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");

    const returnBlock = src.slice(src.indexOf("return ("), src.lastIndexOf(");"));
    expect(returnBlock).not.toContain("mailto:");
    expect(returnBlock).not.toContain(DT_CONTACT_EMAIL);
    expect(returnBlock).toContain('href="#"');

    // Outside the doc comment, the only literal "mailto:" in the file is the
    // template-string prefix inside buildMailtoHref -- not duplicated inline
    // anywhere a server-rendered value (JSX, an href attribute) could carry it.
    const code = src.slice(src.indexOf("*/") + 2);
    expect(code.match(/mailto:/g)?.length).toBe(1);
  });

  it("keeps every digithings-web page contact link on ContactMailto instead of a raw mailto: anchor", async () => {
    const pages = [
      "../app/page.tsx",
      "../app/team/page.tsx",
      "../app/services/page.tsx",
      "../app/legal/privacy/page.tsx",
    ];
    for (const rel of pages) {
      const path = fileURLToPath(new URL(rel, import.meta.url));
      const src = readFileSync(path, "utf8");
      expect(src).not.toContain("mailto:");
      expect(src).toContain("<ContactMailto");
    }
  });
});
