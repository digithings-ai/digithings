/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it, vi } from "vitest";
import { inlineAssetUrls, inlineDomAssets } from "./browser";

describe("inlineAssetUrls", () => {
  it("embeds same-origin fonts and drops every other url", async () => {
    const fetchImpl = vi.fn(async () => {
      return new Response(new Uint8Array([1, 2, 3]), {
        status: 200,
        headers: { "content-type": "font/woff2" },
      });
    });
    const css = [
      'src: url("/_next/static/media/geist.woff2")',
      'src: url("https://fonts.example/remote.woff2")',
    ].join(";");
    const out = await inlineAssetUrls(css, {
      origin: "https://desk.example",
      href: "https://desk.example/chat",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(out).toContain("data:font/woff2;base64,");
    expect(out).not.toContain("fonts.example");
    expect(out).not.toContain("/_next/static/media/geist.woff2");
    expect(fetchImpl).toHaveBeenCalledOnce();
  });
});

describe("inlineDomAssets", () => {
  it("inlines a same-origin image and drops a remote one", async () => {
    const doc = document.implementation.createHTMLDocument("chat");
    doc.body.innerHTML = [
      '<img id="local" src="/logo.png" alt="local">',
      '<img id="remote" src="https://cdn.example/icon.png" alt="remote">',
    ].join("");
    const fetchImpl = vi.fn(async () => {
      return new Response(new Uint8Array([9, 9]), {
        status: 200,
        headers: { "content-type": "image/png" },
      });
    });
    await inlineDomAssets(doc, {
      origin: "https://desk.example",
      href: "https://desk.example/chat",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(doc.getElementById("local")?.getAttribute("src")).toContain("data:image/png;base64,");
    expect(doc.getElementById("remote")?.getAttribute("src")).toBeNull();
    expect(fetchImpl).toHaveBeenCalledOnce();
  });
});
