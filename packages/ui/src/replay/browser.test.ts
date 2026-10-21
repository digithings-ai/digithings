import { describe, expect, it, vi } from "vitest";
import { cssLooksLikeChat, inlineAssetUrls, resolveReplayCss } from "./browser";

describe("resolveReplayCss", () => {
  it("inlines the live sheet when it is the chat stylesheet", async () => {
    const inline = vi.fn(async (css: string) => `${css}/*inlined*/`);
    const bundled = vi.fn(async () => "bundled");
    const css = await resolveReplayCss(".aui-user-message-content { color: red; }", bundled, inline);
    expect(css).toContain("/*inlined*/");
    expect(bundled).not.toHaveBeenCalled();
  });

  it("uses the asset route when the page has no chat rules", async () => {
    const bundled = vi.fn(async () => "bundled");
    await expect(resolveReplayCss("body { margin: 0 }", bundled)).resolves.toBe("bundled");
  });
});

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

describe("cssLooksLikeChat", () => {
  it("recognises the user message and markdown hooks", () => {
    expect(cssLooksLikeChat(".aui-md { }")).toBe(true);
    expect(cssLooksLikeChat("body {}")).toBe(false);
  });
});
