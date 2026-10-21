/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it } from "vitest";
import { inlineDomAssets } from "./browser";
import { snapshotFilename } from "./filename";
import { serializeSnapshot, transformSnapshotDom } from "./snapshot";

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
