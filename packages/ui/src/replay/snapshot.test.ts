/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it } from "vitest";
import { inlineDomAssets, liveSheetText } from "./browser";
import { snapshotFilename } from "./filename";
import { messageAnchor, serializeSnapshot, snapshotSource, transformSnapshotDom } from "./snapshot";

const HEX48 = "cd".repeat(24);
const SECRET = "dgk_live_TESTSECRET99";

function page(): HTMLElement {
  document.documentElement.setAttribute("data-theme", "dark");
  document.head.innerHTML = [
    // A data: href, so happy-dom makes no network request (mocks only).
    '<link rel="stylesheet" href="data:text/css,.x%7B%7D">',
    "<style>.live { color: CanvasText; }</style>",
    "<script>window.__sent = true</script>",
  ].join("");
  document.body.innerHTML = `
    <div data-deployment="Northwind" data-thread-skin="digichat">
      <header>
        <button type="button" id="new-chat" onclick="send()">New</button>
        <a id="settings" href="/settings">Settings</a>
      </header>
      <div class="aui-user-message-content">What is the overnight book?</div>
      <div data-slot="aui_work-chain" data-closed>
        <button data-slot="aui_work-chain-trigger" aria-expanded="false" aria-controls="chain">
          <span data-slot="disclosure-chevron"><span data-slot="dot-matrix-grid"></span></span>
          Worked
        </button>
        <div id="chain" data-slot="aui_work-chain-content" hidden style="height: 0px">
          <div data-slot="tool-fallback-root" data-open>
            <button data-slot="tool-fallback-trigger" aria-expanded="true" aria-controls="tool">
              <span data-slot="disclosure-chevron"></span>
              Used tool
            </button>
            <div id="tool" data-slot="tool-fallback-content">
              result ${SECRET} ${HEX48}
              <a href="https://digithings.ai/docs">docs</a>
            </div>
          </div>
        </div>
      </div>
      <form class="aui-composer-root">
        <textarea class="aui-composer-input"></textarea>
        <button class="aui-composer-send" type="submit">Send</button>
      </form>
      <img id="remote" src="https://cdn.example/icon.png" alt="remote">
    </div>
  `;
  return document.documentElement;
}

describe("snapshotFilename", () => {
  it("uses the deployment, utc minute, and question slug", () => {
    expect(
      snapshotFilename("Northwind", "2026-10-21T15:04:00.000Z", "What is the overnight book?"),
    ).toBe("northwind-2026-10-21-1504-what-is-the-overnight-book.html");
  });

  it("falls back when the deployment and question are empty", () => {
    expect(snapshotFilename("  ", "2026-10-21T15:04:00.000Z", "")).toBe(
      "digichat-2026-10-21-1504-thread.html",
    );
  });

  it("does not put a bare invite key in the file name", () => {
    expect(snapshotFilename("desk", "2026-10-21T15:04:00.000Z", HEX48)).not.toContain(HEX48);
  });

  it("drops id-like words the patterns do not know and cuts at a word", () => {
    const name = snapshotFilename(
      "desk",
      "2026-10-21T15:04:00.000Z",
      "Show me the api key 9f8e7d6c5b4a and explain every single step of the rotation process",
    );
    expect(name).not.toContain("9f8e7d6c5b4a");
    const slug = name.replace(/^desk-2026-10-21-1504-/, "").replace(/\.html$/, "");
    expect(slug.length).toBeLessThanOrEqual(48);
    expect(slug).toBe("show-me-the-api-key-and-explain-every-single");
  });
});

describe("transformSnapshotDom", () => {
  it("keeps the rendered chat, drops the composer, and leaves disclosures expandable", async () => {
    const root = page().cloneNode(true) as HTMLElement;
    transformSnapshotDom(root);
    await inlineDomAssets(root, {
      origin: "https://desk.example",
      href: "https://desk.example/chat",
      fetchImpl: (async () => new Response(null, { status: 404 })) as typeof fetch,
    });
    const html = serializeSnapshot(root, ".aui-user-message-content { font-family: inherit; }");

    expect(html.toLowerCase()).not.toContain("<script");
    expect(html).not.toContain("<textarea");
    expect(html).not.toContain("aui-composer");
    expect(html).not.toContain("onclick");
    expect(html).not.toContain(SECRET);
    expect(html).not.toContain(HEX48);
    expect(html).toContain("[redacted]");
    expect(html).toContain("https://digithings.ai/docs");
    expect(html).not.toContain("cdn.example");
    expect(html).not.toContain("data:text/css");
    expect(html).not.toMatch(/<link\b/i);
    expect(html).toContain("What is the overnight book?");
    expect(html).toContain("data-snapshot-css");
    expect(html).toContain(".aui-user-message-content");

    const chain = root.querySelector("[data-slot='aui_work-chain']");
    expect(chain?.tagName).toBe("DETAILS");
    expect(chain?.hasAttribute("open")).toBe(false);
    const summary = chain?.querySelector("summary");
    expect(summary?.textContent).toContain("Worked");
    const tool = root.querySelector("[data-slot='tool-fallback-root']");
    expect(tool?.tagName).toBe("DETAILS");
    expect(tool?.hasAttribute("open")).toBe(true);
    expect(html).toContain("result");

    expect(root.querySelector("#new-chat")?.tagName).toBe("SPAN");
    expect(root.querySelector("#new-chat")?.hasAttribute("data-snapshot-static")).toBe(true);
    expect(root.querySelector("#settings")?.hasAttribute("href")).toBe(false);
    expect(root.querySelector("#remote")?.hasAttribute("src")).toBe(false);
  });
});

describe("active thread only", () => {
  it("leaves the other thread and the memory sidebar out of the file", () => {
    document.body.innerHTML = [
      '<aside class="dc-thread-list" data-memory-thread-list>',
      "<span>Other client positions</span>",
      "</aside>",
      '<div class="aui-thread-root">',
      '<div class="aui-user-message-content">Visible other thread</div>',
      "</div>",
      '<div class="aui-thread-root" data-active="true">',
      '<div class="aui-user-message-content">What is the overnight book?</div>',
      "</div>",
    ].join("");
    const shell = snapshotSource(document);
    expect(shell).not.toBeNull();
    transformSnapshotDom(shell!);
    const html = serializeSnapshot(shell!, "");
    expect(html).toContain("What is the overnight book?");
    expect(html).not.toContain("Other client positions");
    expect(html).not.toContain("Visible other thread");
    expect(html).not.toContain("data-memory-thread-list");
  });
});

describe("deployment hide rules", () => {
  it("drops sources and a hidden model picker, and keeps the stock scope", () => {
    document.head.innerHTML = [
      "<style>",
      '[data-stock-product] [data-message-part-type^="source"],',
      "[data-stock-product] a[data-source],",
      "[data-stock-product] [data-deploy-model-picker] { display: none !important; }",
      "</style>",
    ].join("");
    document.body.innerHTML = [
      '<div data-stock-product data-deployment="Northwind" data-tenant-id="tenant-marker" data-thread-skin="digichat">',
      '<aside class="dc-thread-list">Other client positions</aside>',
      '<div class="aui-thread-root" data-deployment="Northwind">',
      '<div class="aui-user-message-content">What is the overnight book?</div>',
      '<div data-message-part-type="source-url">Hidden source body</div>',
      '<a data-source href="https://example.com/src">source link text</a>',
      "<div data-deploy-model-picker>picker-model-name</div>",
      '<div style="visibility: hidden">covered picker note</div>',
      '<div data-slot="aui_work-chain">',
      '<button data-slot="aui_work-chain-trigger" aria-expanded="false" aria-controls="chain">',
      "Worked",
      "</button>",
      '<div id="chain" data-slot="aui_work-chain-content" hidden>folded tool result</div>',
      "</div>",
      "</div>",
      "</div>",
    ].join("");
    const shell = snapshotSource(document);
    expect(shell).not.toBeNull();
    expect(
      shell!.querySelector(".aui-thread-root")?.closest("[data-stock-product]"),
    ).not.toBeNull();
    expect(document.body.textContent).toContain("Hidden source body");
    transformSnapshotDom(shell!);
    const html = serializeSnapshot(shell!, "");
    expect(html).toContain("What is the overnight book?");
    expect(html).toContain("folded tool result");
    expect(html).toContain("data-stock-product");
    expect(html).not.toContain("data-deployment");
    expect(html).not.toContain("data-tenant");
    expect(html).not.toContain("tenant-marker");
    expect(document.body.innerHTML).toContain("data-deployment");
    expect(html).not.toContain("Hidden source body");
    expect(html).not.toContain("source link text");
    expect(html).not.toContain("picker-model-name");
    expect(html).not.toContain("covered picker note");
    expect(html).not.toContain("Other client positions");
  });

  it("drops a source inside a folded panel when sources are off", () => {
    document.head.innerHTML = [
      "<style>",
      '[data-stock-product] [data-message-part-type^="source"],',
      "[data-stock-product] a[data-source] { display: none !important; }",
      "</style>",
    ].join("");
    document.body.innerHTML = [
      "<div data-stock-product>",
      '<div class="aui-thread-root">',
      '<div class="aui-user-message-content">What is the overnight book?</div>',
      '<div id="chain" data-slot="aui_work-chain-content" hidden>',
      "<p>folded tool result</p>",
      '<div data-message-part-type="source-url">Panel source body</div>',
      '<a data-source href="https://example.com/inside">panel source link</a>',
      "</div>",
      "</div>",
      "</div>",
    ].join("");
    const shell = snapshotSource(document);
    expect(shell).not.toBeNull();
    transformSnapshotDom(shell!);
    const html = serializeSnapshot(shell!, "");
    expect(html).toContain("What is the overnight book?");
    expect(html).toContain("folded tool result");
    expect(html).not.toContain("Panel source body");
    expect(html).not.toContain("panel source link");
    expect(document.body.textContent).toContain("Panel source body");
  });

  it("inlines the deployment hide rules and still drops what they hide", () => {
    const rules = [
      '[data-stock-product] [data-slot="aui_reasoning"], [data-stock-product] .aui-reasoning-root { display: none !important; }',
      '[data-stock-product] [data-slot="aui_tool-fallback"], [data-stock-product] .aui-tool-fallback-root { display: none !important; }',
      '[data-stock-product] [data-message-part-type^="source"], [data-stock-product] a[data-source] { display: none !important; }',
      '[data-stock-product] [data-slot="aui_composer-add-attachment"], [data-stock-product] .aui-composer-add-attachment { display: none !important; }',
      '[data-stock-product] [data-slot="aui_branch-picker"], [data-stock-product] .aui-branch-picker-root { display: none !important; }',
      "[data-stock-product] [data-deploy-model-picker] { display: none !important; }",
    ].join("\n");
    document.head.innerHTML = `<style>${rules}</style>`;
    document.body.innerHTML = [
      '<div data-stock-product data-deployment="Northwind">',
      '<div class="aui-thread-root">',
      '<div class="aui-user-message-content">What is the overnight book?</div>',
      "<div data-deploy-model-picker>picker-model-name</div>",
      '<div id="chain" data-slot="aui_work-chain-content" hidden>',
      "<p>folded tool result</p>",
      '<div data-slot="aui_reasoning">hidden reasoning text</div>',
      '<div data-message-part-type="source-url">Panel source body</div>',
      "</div>",
      "</div>",
      "</div>",
    ].join("");
    const shell = snapshotSource(document);
    expect(shell).not.toBeNull();
    transformSnapshotDom(shell!);
    const html = serializeSnapshot(shell!, rules);
    expect(html).toContain("folded tool result");
    expect(html).toContain('[data-message-part-type^="source"]');
    expect(html).toContain("[data-deploy-model-picker]");
    expect(html).not.toContain("Panel source body");
    expect(html).not.toContain("hidden reasoning text");
    expect(html).not.toContain("picker-model-name");
  });
});

describe("one interaction", () => {
  it("keeps the question and that answer, and leaves the rest of the thread", () => {
    document.body.innerHTML = [
      '<div class="aui-thread-root" data-deployment="Northwind">',
      '<div data-role="user"><div class="aui-user-message-content">First question</div></div>',
      '<div data-role="assistant"><div class="aui-assistant-message-content">First answer</div></div>',
      '<div data-role="user"><div class="aui-user-message-content">Second question</div></div>',
      '<div data-role="assistant">',
      '<div class="aui-assistant-message-content">Second answer</div>',
      '<button id="export-html">Export as HTML</button>',
      "</div>",
      "</div>",
    ].join("");
    const anchor = document.getElementById("export-html");
    expect(anchor).not.toBeNull();
    const shell = snapshotSource(document, anchor);
    expect(shell).not.toBeNull();
    const html = serializeSnapshot(shell!, "");
    expect(html).toContain("Second question");
    expect(html).toContain("Second answer");
    expect(html).not.toContain("First question");
    expect(html).not.toContain("First answer");
    expect(document.body.textContent).toContain("First question");
  });

  it("does not fall back to the thread when the anchor sits outside it", () => {
    document.body.innerHTML = [
      '<div class="aui-thread-root">',
      '<div data-role="user"><div class="aui-user-message-content">Only question</div></div>',
      '<div data-role="assistant"><div class="aui-assistant-message-content">Only answer</div></div>',
      "</div>",
      '<button id="ported">Export as HTML</button>',
    ].join("");
    const anchor = document.getElementById("ported");
    expect(anchor).not.toBeNull();
    expect(snapshotSource(document, anchor)).toBeNull();
  });

  it("scopes by message id while an open menu hides the thread from the page", () => {
    document.body.innerHTML = [
      '<div aria-hidden="true">',
      '<div class="aui-thread-root">',
      '<div data-role="user"><div class="aui-user-message-content">First question</div></div>',
      '<div data-role="assistant" data-message-id="a1">',
      '<div class="aui-assistant-message-content">First answer</div>',
      "</div>",
      '<div data-role="user"><div class="aui-user-message-content">Second question</div></div>',
      '<div data-role="assistant" data-message-id="a2">',
      '<div class="aui-assistant-message-content">Second answer</div>',
      '<button id="more">More</button>',
      "</div>",
      "</div>",
      "</div>",
      '<div role="menu"><button>Export as HTML</button></div>',
    ].join("");
    expect(snapshotSource(document)).toBeNull();
    const trigger = document.getElementById("more");
    expect(trigger).not.toBeNull();
    expect(messageAnchor(trigger, "a1")).toBeNull();
    const anchor = messageAnchor(trigger, "a2");
    expect(anchor).not.toBeNull();
    const shell = snapshotSource(document, anchor);
    expect(shell).not.toBeNull();
    const html = serializeSnapshot(shell!, "");
    expect(html).toContain("Second question");
    expect(html).toContain("Second answer");
    expect(html).not.toContain("First question");
    expect(html).not.toContain("First answer");
  });

  it("resolves the trigger's message when an earlier copy has the same id", () => {
    document.body.innerHTML = [
      "<div hidden>",
      '<div class="aui-thread-root">',
      '<div data-role="user"><div class="aui-user-message-content">Embed question</div></div>',
      '<div data-role="assistant" data-message-id="dup">',
      '<div class="aui-assistant-message-content">embed-duplicate-token</div>',
      "</div>",
      "</div>",
      "</div>",
      '<div class="aui-thread-root">',
      '<div data-role="user"><div class="aui-user-message-content">Real question</div></div>',
      '<div data-role="assistant" data-message-id="dup">',
      '<div class="aui-assistant-message-content">Real answer</div>',
      '<button id="more">More</button>',
      "</div>",
      "</div>",
    ].join("");
    const trigger = document.getElementById("more");
    expect(trigger).not.toBeNull();
    const anchor = messageAnchor(trigger, "dup");
    expect(anchor?.textContent).toContain("Real answer");
    expect(anchor?.textContent).not.toContain("embed-duplicate-token");
    const shell = snapshotSource(document, anchor);
    expect(shell).not.toBeNull();
    const html = serializeSnapshot(shell!, "");
    expect(html).toContain("Real question");
    expect(html).toContain("Real answer");
    expect(html).not.toContain("embed-duplicate-token");
    expect(html).not.toContain("Embed question");
  });

  it("drops the open menu's page lock and keeps the question", () => {
    document.head.innerHTML =
      "<style>body[data-scroll-locked]{overflow:hidden}.ok{color:CanvasText}</style>";
    document.body.setAttribute("data-scroll-locked", "1");
    document.body.setAttribute("style", "pointer-events: none; color: CanvasText");
    document.body.innerHTML = [
      '<div aria-hidden="true" data-aria-hidden="true" inert>',
      '<div class="aui-thread-root">',
      '<div data-role="user"><div class="aui-user-message-content">Locked question</div></div>',
      '<div data-role="assistant" data-message-id="a2">',
      '<span aria-hidden="true">decorative marker</span>',
      '<div id="kept-inert" inert>kept inert note</div>',
      '<div class="aui-assistant-message-content">Locked answer</div>',
      '<button id="more">More</button>',
      "</div>",
      "</div>",
      "</div>",
    ].join("");
    const trigger = document.getElementById("more");
    const anchor = messageAnchor(trigger, "a2");
    expect(anchor).not.toBeNull();
    const shell = snapshotSource(document, anchor);
    expect(shell).not.toBeNull();
    const css = liveSheetText(document);
    expect(css).not.toContain("data-scroll-locked");
    expect(css).toContain(".ok");
    const html = serializeSnapshot(shell!, `${css}\nbody[data-scroll-locked]{overflow:hidden}`);
    expect(html).toContain("Locked question");
    expect(html).toContain("Locked answer");
    expect(html).not.toContain("data-aria-hidden");
    expect(html).not.toContain("data-scroll-locked");
    expect(html).toContain(".ok");
    const parsed = new DOMParser().parseFromString(html, "text/html");
    const thread = parsed.querySelector(".aui-thread-root");
    expect(thread?.parentElement?.hasAttribute("aria-hidden")).toBe(false);
    expect(thread?.parentElement?.hasAttribute("inert")).toBe(false);
    expect(parsed.body.hasAttribute("inert")).toBe(false);
    expect(parsed.documentElement.hasAttribute("inert")).toBe(false);
    expect(parsed.querySelector("[aria-hidden='true']")?.textContent).toContain(
      "decorative marker",
    );
    expect(parsed.getElementById("kept-inert")?.hasAttribute("inert")).toBe(true);
    expect(parsed.body.getAttribute("style") ?? "").not.toMatch(/pointer-events/i);
    expect(parsed.body.getAttribute("style") ?? "").toMatch(/color/i);
    expect(document.body.hasAttribute("data-scroll-locked")).toBe(true);
    expect(document.body.getAttribute("style") ?? "").toMatch(/pointer-events/i);
    document.body.removeAttribute("data-scroll-locked");
    document.body.removeAttribute("style");
  });
});

describe("refresh meta", () => {
  it("strips a refresh meta in the thread and inside a template", () => {
    document.body.innerHTML =
      '<div class="aui-thread-root"><div class="aui-user-message-content">book</div></div>';
    const thread = document.querySelector(".aui-thread-root");
    expect(thread).not.toBeNull();
    const meta = document.createElement("meta");
    meta.setAttribute("http-equiv", "Refresh");
    meta.setAttribute("content", "0;url=https://evil.example/body");
    thread!.append(meta);
    const template = document.createElement("template");
    const nested = document.createElement("meta");
    nested.setAttribute("http-equiv", "refresh");
    nested.setAttribute("content", "0;url=https://evil.example/tpl");
    template.content.append(nested);
    thread!.append(template);
    const shell = snapshotSource(document);
    expect(shell).not.toBeNull();
    transformSnapshotDom(shell!);
    const html = serializeSnapshot(shell!, "");
    expect(html.toLowerCase()).not.toContain("evil.example");
    expect(html.toLowerCase()).not.toMatch(/http-equiv=["']refresh/);
  });
});

describe("snapshot stylesheet", () => {
  it("escapes style breakout and puts a strict csp first", () => {
    document.body.innerHTML = [
      '<div class="aui-thread-root" data-active="true">',
      '<button type="button" onclick="alert(1)">New</button>',
      '<div class="aui-user-message-content">book</div>',
      "</div>",
    ].join("");
    const shell = snapshotSource(document);
    expect(shell).not.toBeNull();
    transformSnapshotDom(shell!);
    const css = 'p{content:"</style><img src=x onerror=alert(1)>" }';
    const html = serializeSnapshot(shell!, css);
    const parsed = new DOMParser().parseFromString(html, "text/html");
    expect(parsed.querySelector("script")).toBeNull();
    expect(parsed.querySelector("img")).toBeNull();
    for (const el of parsed.querySelectorAll("*")) {
      for (const attr of el.attributes) {
        expect(attr.name.toLowerCase().startsWith("on")).toBe(false);
      }
    }
    const style = parsed.querySelector("style");
    expect(style?.textContent ?? "").not.toContain("<");
    expect(html).toContain("\\3c ");
    const first = parsed.querySelector("head")?.firstElementChild;
    expect(first?.getAttribute("http-equiv")?.toLowerCase()).toBe("content-security-policy");
    expect(first?.getAttribute("content")).toContain("default-src 'none'");
    expect(first?.getAttribute("content")).toContain("style-src 'unsafe-inline'");
    expect(first?.getAttribute("content")).toContain("img-src data:");
    expect(first?.getAttribute("content")).toContain("form-action 'none'");
  });
});

describe("link schemes", () => {
  it("drops javascript:, vbscript: and data: hrefs in chat content and keeps https", () => {
    const doc = document.implementation.createHTMLDocument("chat");
    doc.body.innerHTML = [
      '<div class="aui-md">',
      '<a id="js" href="JavaScript:alert(1)">a</a>',
      '<a id="vb" href="vbscript:msgbox">b</a>',
      '<a id="data" href="data:text/html,x">c</a>',
      '<a id="ok" href="https://digithings.ai/docs">d</a>',
      "</div>",
    ].join("");
    transformSnapshotDom(doc.documentElement);
    for (const id of ["js", "vb", "data"]) {
      expect(doc.getElementById(id)?.hasAttribute("href")).toBe(false);
    }
    expect(doc.getElementById("ok")?.getAttribute("href")).toBe("https://digithings.ai/docs");
  });
});
