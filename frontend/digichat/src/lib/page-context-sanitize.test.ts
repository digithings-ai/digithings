/** @vitest-environment happy-dom */
import { afterEach, describe, expect, it } from "vitest";
import { MAX_PAGE_CONTEXT_HTML_CHARS } from "@/lib/embed-page-context-messages";
import {
  PAGE_CONTEXT_PRIVATE_ATTR,
  extractPageContext,
  extractPageHtml,
  sanitizePageHtml,
} from "@/lib/page-context-sanitize";

function secretsRemain(html: string, secrets: readonly string[]): string[] {
  return secrets.filter((s) => html.includes(s));
}

describe("sanitizePageHtml — structural allowlist (#3602)", () => {
  it("keeps visible layout text and drops scripts/handlers", () => {
    const clean = sanitizePageHtml(
      '<div onclick="x()"><script>bad()</script><p>ok</p></div>',
    );
    expect(clean).toContain("<p>ok</p>");
    expect(clean.toLowerCase()).not.toContain("script");
    expect(clean).not.toContain("onclick");
    expect(clean).not.toContain("bad()");
  });

  it("drops nested hidden / inert / aria-hidden subtrees", () => {
    const clean = sanitizePageHtml(
      "<main>" +
        "<p>Visible heading</p>" +
        "<div hidden><span>HIDDEN-NESTED</span></div>" +
        '<section aria-hidden="true"><p>ARIA-HIDDEN-SECRET</p></section>' +
        "<aside inert><p>INERT-SECRET</p></aside>" +
        '<div aria-hidden="TRUE"><span>ARIA-MIXED-CASE</span></div>' +
        "</main>",
    );
    expect(clean).toContain("Visible heading");
    expect(secretsRemain(clean, [
      "HIDDEN-NESTED",
      "ARIA-HIDDEN-SECRET",
      "INERT-SECRET",
      "ARIA-MIXED-CASE",
    ])).toEqual([]);
  });

  it("drops mixed-case password and unquoted hidden inputs", () => {
    const clean = sanitizePageHtml(
      "<form>" +
        "<label>Email</label>" +
        "<INPUT TYPE=PASSWORD value=s3cret-pass>" +
        "<input TYPE='Hidden' name=csrf value=csrf-token-live>" +
        "<p>After fields</p>" +
        "</form>",
    );
    expect(clean).toContain("Email");
    expect(clean).toContain("After fields");
    expect(secretsRemain(clean, ["s3cret-pass", "csrf-token-live"])).toEqual([]);
  });

  it("drops autofill password fields even when type is text", () => {
    const clean = sanitizePageHtml(
      '<input type="text" autocomplete="current-password" value="autofill-secret">' +
        '<input autocomplete="new-password" value="new-pass-secret">' +
        '<input autocomplete="cc-number" value="4111111111111111">' +
        "<p>ok</p>",
    );
    expect(clean).toContain("ok");
    expect(secretsRemain(clean, [
      "autofill-secret",
      "new-pass-secret",
      "4111111111111111",
    ])).toEqual([]);
  });

  it("strips inline-hidden nodes and input values", () => {
    const clean = sanitizePageHtml(
      '<p style="display:none">DISPLAY-NONE-SECRET</p>' +
        '<p style="visibility:hidden">VIS-HIDDEN-SECRET</p>' +
        '<input type="text" value="typed-secret">' +
        "<textarea>area-secret</textarea>" +
        "<p>visible</p>",
    );
    expect(clean).toContain("visible");
    expect(secretsRemain(clean, [
      "DISPLAY-NONE-SECRET",
      "VIS-HIDDEN-SECRET",
      "typed-secret",
      "area-secret",
    ])).toEqual([]);
  });

  it("strips secret-bearing URLs and javascript hrefs", () => {
    const clean = sanitizePageHtml(
      '<a href="/research?token=tok_live&amp;x=1">Research</a>' +
        '<a href="javascript:alert(1)">XSS</a>' +
        '<a href="https://api.example/v1?api_key=k-secret">API</a>',
    );
    expect(clean).toContain("Research");
    expect(clean).toContain("XSS");
    expect(clean).toContain("API");
    expect(secretsRemain(clean, ["tok_live", "k-secret", "javascript:"])).toEqual(
      [],
    );
    expect(clean).not.toMatch(/href\s*=\s*["'][^"']*\?/i);
  });

  it("strips framework metadata attributes", () => {
    const clean = sanitizePageHtml(
      '<div data-reactid=".0" ng-reflect-model="secret-model" wire:id="x">' +
        "<p>ok</p></div>",
    );
    expect(clean).toContain("ok");
    expect(clean).not.toContain("data-reactid");
    expect(clean).not.toContain("ng-reflect");
    expect(clean).not.toContain("wire:id");
    expect(clean).not.toContain("secret-model");
  });

  it("honors the opt-out marker on a region", () => {
    const clean = sanitizePageHtml(
      `<p>public</p><aside ${PAGE_CONTEXT_PRIVATE_ATTR}><p>PRIVATE-REGION</p></aside>`,
    );
    expect(clean).toContain("public");
    expect(clean).not.toContain("PRIVATE-REGION");
  });

  it("survives malformed markup without leaking script or svg payloads", () => {
    const clean = sanitizePageHtml(
      '<p>ok</p><script src="https://evil.example/x.js"></script>' +
        "<p>still</p><svg onload=alert(1)></svg>" +
        "<img src=x onerror=alert(1)><div><p>nested",
    );
    expect(clean).toContain("ok");
    expect(clean).toContain("still");
    expect(clean).toContain("nested");
    expect(clean.toLowerCase()).not.toContain("<script");
    expect(clean.toLowerCase()).not.toContain("onload");
    expect(clean.toLowerCase()).not.toContain("onerror");
    expect(clean.toLowerCase()).not.toContain("<svg");
    expect(clean.toLowerCase()).not.toContain("<img");
    expect(clean).not.toContain("evil.example");
  });

  it("does not truncate mid-tag", () => {
    const long = `<div class="wrap"><p>${"y".repeat(MAX_PAGE_CONTEXT_HTML_CHARS + 80)}</p></div>`;
    const clean = sanitizePageHtml(long);
    expect(clean.length).toBeLessThanOrEqual(MAX_PAGE_CONTEXT_HTML_CHARS);
    expect(clean).not.toMatch(/<[^>]*$/);
  });
});

describe("extractPageHtml / extractPageContext — live DOM (#3602)", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    document.head.querySelectorAll("style[data-pc-test]").forEach((n) => n.remove());
  });

  it("drops CSS-hidden nodes using computed style on the live tree", () => {
    const style = document.createElement("style");
    style.setAttribute("data-pc-test", "1");
    style.textContent = ".pc-hide { display: none } .pc-invis { visibility: hidden }";
    document.head.appendChild(style);
    document.body.innerHTML =
      "<main><p>Visible</p><p class='pc-hide'>CSS-DISPLAY-SECRET</p>" +
      "<p class='pc-invis'>CSS-VIS-SECRET</p></main>";

    const html = extractPageHtml();
    const { text } = extractPageContext();
    expect(html).toContain("Visible");
    expect(text).toContain("Visible");
    expect(html).not.toContain("CSS-DISPLAY-SECRET");
    expect(html).not.toContain("CSS-VIS-SECRET");
    expect(text).not.toContain("CSS-DISPLAY-SECRET");
    expect(text).not.toContain("CSS-VIS-SECRET");
  });

  it("prefers main and strips popup chrome plus private regions", () => {
    document.body.innerHTML =
      "<header>chrome</header>" +
      "<main><h1>Brief</h1><p>House book</p>" +
      `<div ${PAGE_CONTEXT_PRIVATE_ATTR}>API-KEY-BLOCK</div></main>` +
      '<div data-digichat-popup="1">Ask digichat launcher</div>';

    const html = extractPageHtml();
    expect(html).toContain("Brief");
    expect(html).toContain("House book");
    expect(html).not.toContain("API-KEY-BLOCK");
    expect(html).not.toContain("Ask digichat launcher");
    expect(html).not.toContain("chrome");
  });
});
