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

  it("drops a same-origin response that is not an image or a font", async () => {
    const fetchImpl = vi.fn(async () => {
      return new Response('{"password":"css-secret-99","token":"css-token-99"}', {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    const out = await inlineAssetUrls('src: url("/api/settings")', {
      origin: "https://desk.example",
      href: "https://desk.example/chat",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(out).not.toContain("css-secret-99");
    expect(out).not.toContain("css-token-99");
    expect(out).not.toContain("data:");
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

  it("does not inline a same-origin json body", async () => {
    const doc = document.implementation.createHTMLDocument("chat");
    doc.body.innerHTML = '<img id="api" src="/api/conversations" alt="">';
    const fetchImpl = vi.fn(async () => {
      return new Response('{"password":"json-secret-99","token":"json-token-99"}', {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    await inlineDomAssets(doc, {
      origin: "https://desk.example",
      href: "https://desk.example/chat",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    const src = doc.getElementById("api")?.getAttribute("src") ?? "";
    expect(src).not.toContain("json-secret-99");
    expect(src).not.toContain("json-token-99");
    expect(src.startsWith("data:")).toBe(false);
  });
});

describe("downloadThreadSnapshot (end to end)", () => {
  it("clones, freezes, redacts and downloads a well-formed file", async () => {
    vi.resetModules();
    const saved: Array<{ name: string; body: string }> = [];
    vi.doMock("../components/chat/transcript", () => ({
      downloadTextFile: (name: string, body: string) => void saved.push({ name, body }),
    }));
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 404 })),
    );
    const { downloadThreadSnapshot } = await import("./browser");
    const doc = document.implementation.createHTMLDocument("chat");
    doc.body.innerHTML = [
      '<div class="aui-thread-root" data-deployment="Northwind">',
      '<div class="aui-user-message-content">How do I set the Cookie header?</div>',
      '<div class="aui-md"><pre><code>Cookie: session=abc123456</code></pre><p>Then reload.</p></div>',
      '<pre data-slot="tool-fallback-json"><span>{</span>\n  <span>"password"</span>: <span>"hunter2"</span>\n<span>}</span></pre>',
      '<form class="aui-composer-root"><textarea></textarea></form>',
      "</div>",
    ].join("");
    await downloadThreadSnapshot(doc, "2026-10-21T15:04:00.000Z");
    vi.unstubAllGlobals();
    vi.doUnmock("../components/chat/transcript");

    expect(saved).toHaveLength(1);
    const { name, body } = saved[0]!;
    expect(name).toBe("northwind-2026-10-21-1504-how-do-i-set-the-cookie-header.html");
    expect(body).not.toContain("abc123456");
    expect(body).not.toContain("hunter2");
    expect(body).not.toContain("aui-composer");
    const parsed = new DOMParser().parseFromString(body, "text/html");
    expect(parsed.querySelector(".aui-md p")?.textContent).toBe("Then reload.");
    expect(parsed.querySelector(".aui-md pre")?.textContent).toMatch(
      /^Cookie: (session=)?\[redacted\]$/,
    );
  });

  it("shows an error and does not download when the page has no thread", async () => {
    vi.resetModules();
    const saved: Array<{ name: string; body: string }> = [];
    vi.doMock("../components/chat/transcript", () => ({
      downloadTextFile: (name: string, body: string) => void saved.push({ name, body }),
    }));
    const { downloadThreadSnapshot } = await import("./browser");
    const doc = document.implementation.createHTMLDocument("chat");
    doc.body.innerHTML = "<p>Nothing open</p>";
    await expect(downloadThreadSnapshot(doc, "2026-10-21T15:04:00.000Z")).rejects.toThrow(
      /no open thread/i,
    );
    expect(saved).toHaveLength(0);
    expect(doc.querySelector("[role='alert']")?.textContent).toMatch(/no open thread/i);
    expect(doc.body.textContent).toContain("Nothing open");
    vi.doUnmock("../components/chat/transcript");
  });

  it("shows an error and does not download when the message id is not in the thread", async () => {
    vi.resetModules();
    const saved: Array<{ name: string; body: string }> = [];
    vi.doMock("../components/chat/transcript", () => ({
      downloadTextFile: (name: string, body: string) => void saved.push({ name, body }),
    }));
    const { downloadMessageSnapshot } = await import("./browser");
    const doc = document.implementation.createHTMLDocument("chat");
    doc.body.innerHTML = [
      '<div class="aui-thread-root">',
      '<div data-role="user" data-message-id="user-1">Other question</div>',
      '<div data-role="assistant" data-message-id="asst-1">Other answer</div>',
      "</div>",
    ].join("");
    await expect(
      downloadMessageSnapshot(doc, "2026-10-21T15:04:00.000Z", "missing"),
    ).rejects.toThrow(/couldn't find that message/i);
    await expect(
      downloadMessageSnapshot(doc, "2026-10-21T15:04:00.000Z", "user-1"),
    ).rejects.toThrow(/couldn't find that message/i);
    expect(saved).toHaveLength(0);
    expect(doc.querySelector("[role='alert']")?.textContent).toMatch(/couldn't find that message/i);
    expect(doc.body.textContent).toContain("Other question");
    vi.doUnmock("../components/chat/transcript");
  });
});
