import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_DIGICHAT_EMBED_ORIGIN,
  digithingsCsp,
  embedOriginForChat,
  frameSrcForCsp,
  openwikiCsp,
  renderCloudflareHeaders,
  resolveDigichatEmbedOrigin,
} from "./security-headers.mjs";

const headersPath = resolve(__dirname, "../public/_headers");

type HeaderBlock = { pattern: string; lines: string[] };

/** Parse a Cloudflare Pages `_headers` body into (pattern, header lines) blocks. */
function parseHeaderBlocks(text: string): HeaderBlock[] {
  const blocks: HeaderBlock[] = [];
  let current: HeaderBlock | null = null;
  for (const line of text.split("\n")) {
    if (!line.trim() || line.trimStart().startsWith("#")) continue;
    if (!line.startsWith(" ") && !line.startsWith("\t")) {
      current = { pattern: line.trim(), lines: [] };
      blocks.push(current);
      continue;
    }
    if (current) current.lines.push(line.trim());
  }
  return blocks;
}

/**
 * Effective `Content-Security-Policy` values a browser would receive for a path,
 * simulating Cloudflare's inheritance + `!` detach semantics: a match inherits
 * every earlier (more pervasive) rule's headers, and `! Name` removes the
 * inherited value before this rule's own value is attached. Detach applies only
 * to inherited headers, never to a value in the same block.
 */
function effectiveCspFor(blocks: HeaderBlock[], path: string): string[] {
  let values: string[] = [];
  for (const block of blocks) {
    const matches =
      block.pattern === "/*" || path.startsWith(block.pattern.replace(/\*$/, ""));
    if (!matches) continue;
    for (const line of block.lines) {
      if (line.startsWith("! ")) {
        if (line.slice(2).trim() === "Content-Security-Policy") values = [];
        continue;
      }
      const [name, ...rest] = line.split(":");
      if (name.trim() === "Content-Security-Policy") values.push(rest.join(":").trim());
    }
  }
  return values;
}

describe("digithings-web security-headers", () => {
  it("resolves embed origin from NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN", () => {
    expect(
      resolveDigichatEmbedOrigin({
        NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN: "https://tunnel.example/embed",
      }),
    ).toBe("https://tunnel.example");
    expect(resolveDigichatEmbedOrigin({})).toBeNull();
    expect(
      resolveDigichatEmbedOrigin({
        NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN: "not a url",
      }),
    ).toBeNull();
  });

  it("uses env origin for CSP frame-src, else production default", () => {
    expect(
      frameSrcForCsp({
        NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN: "https://staging-chat.example",
      }),
    ).toBe("https://staging-chat.example");
    expect(frameSrcForCsp({})).toBe(DEFAULT_DIGICHAT_EMBED_ORIGIN);
    expect(DEFAULT_DIGICHAT_EMBED_ORIGIN).toBe("https://digithings.ai");
    expect(digithingsCsp("https://staging-chat.example")).toContain(
      "frame-src https://staging-chat.example",
    );
  });

  it("aligns /chat iframe origin with CSP (Containers same-host default)", () => {
    expect(embedOriginForChat({})).toBe("https://digithings.ai");
    expect(embedOriginForChat({})).toBe(frameSrcForCsp({}));
  });

  it("keeps committed _headers aligned with default CSP", () => {
    const text = readFileSync(headersPath, "utf8");
    const defaultCsp = digithingsCsp(DEFAULT_DIGICHAT_EMBED_ORIGIN);
    expect(text).toContain(defaultCsp);
    expect(text).not.toMatch(/frame-src 'none'/);
    expect(text).toMatch(/frame-ancestors 'none'/);
    expect(defaultCsp).toContain("worker-src 'self' blob:");
    expect(defaultCsp).toContain("connect-src 'self' https://api.github.com");
    expect(renderCloudflareHeaders(DEFAULT_DIGICHAT_EMBED_ORIGIN)).toContain(
      defaultCsp,
    );
  });

  // /openwiki/* exception for the openwiki visualizer export (#3696): pinned
  // jsDelivr scripts + Google Fonts only, everything else as strict as /*.
  it("renders an /openwiki/* exception scoped to the visualizer's needs", () => {
    const text = renderCloudflareHeaders(DEFAULT_DIGICHAT_EMBED_ORIGIN);
    expect(text).toContain("/openwiki/*");
    const wiki = openwikiCsp();
    expect(text).toContain(wiki);
    expect(wiki).toContain("script-src 'self' https://cdn.jsdelivr.net");
    expect(wiki).toContain("https://fonts.googleapis.com");
    expect(wiki).toContain("https://fonts.gstatic.com");
    expect(wiki).not.toContain("frame-src 'none'");
    expect(wiki).toContain("frame-ancestors 'none'");
    expect(wiki).toContain("object-src 'none'");
    expect(wiki).not.toContain("https://api.github.com");
  });

  // #4206: /openwiki/* inherits the strict /* CSP, so the browser enforces the
  // INTERSECTION of the two and the visualizer's jsDelivr scripts never load.
  // The /openwiki/* rule must detach the inherited CSP (Cloudflare `!` syntax).
  it("detaches the inherited /* CSP on /openwiki/* (no double-CSP intersection)", () => {
    const text = renderCloudflareHeaders(DEFAULT_DIGICHAT_EMBED_ORIGIN);
    const blocks = parseHeaderBlocks(text);
    const wikiBlock = blocks.find((b) => b.pattern === "/openwiki/*");
    expect(wikiBlock).toBeDefined();
    expect(wikiBlock?.lines).toContain("! Content-Security-Policy");

    // The detach lives only in the /openwiki/* block; /* is untouched.
    expect(text.match(/^\s*! Content-Security-Policy$/gm)).toHaveLength(1);

    const strict = digithingsCsp(DEFAULT_DIGICHAT_EMBED_ORIGIN);
    const wiki = openwikiCsp();

    // Exactly one effective CSP reaches the browser on each path.
    expect(effectiveCspFor(blocks, "/openwiki/index.html")).toEqual([wiki]);
    expect(effectiveCspFor(blocks, "/openwiki/")).toEqual([wiki]);
    expect(effectiveCspFor(blocks, "/docs/api/")).toEqual([strict]);

    // The surviving wiki CSP keeps the visualizer's sources; the /* page policy
    // still does not grant jsDelivr.
    expect(effectiveCspFor(blocks, "/openwiki/index.html")[0]).toContain(
      "https://cdn.jsdelivr.net",
    );
    expect(effectiveCspFor(blocks, "/docs/api/")[0]).not.toContain(
      "https://cdn.jsdelivr.net",
    );
  });

  it("committed _headers carries the /openwiki/* CSP detach", () => {
    const text = readFileSync(headersPath, "utf8");
    const blocks = parseHeaderBlocks(text);
    const wikiBlock = blocks.find((b) => b.pattern === "/openwiki/*");
    expect(wikiBlock?.lines).toContain("! Content-Security-Policy");
    expect(effectiveCspFor(blocks, "/openwiki/index.html")).toEqual([
      openwikiCsp(),
    ]);
    expect(effectiveCspFor(blocks, "/")).toEqual([
      digithingsCsp(DEFAULT_DIGICHAT_EMBED_ORIGIN),
    ]);
  });
});
