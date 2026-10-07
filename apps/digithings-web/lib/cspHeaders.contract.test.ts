import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_DIGICHAT_EMBED_ORIGIN,
  DEFAULT_MARKET_DATA_ORIGIN,
  digithingsCsp,
  embedOriginForChat,
  frameSrcForCsp,
  marketDataOriginForCsp,
  openwikiCsp,
  renderCloudflareHeaders,
  resolveDigichatEmbedOrigin,
  resolveMarketDataOrigin,
  resolveSupabaseOrigin,
  supabaseOriginForCsp,
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
/**
 * Effective values of one header a browser would receive for a path, using the
 * same Cloudflare inheritance + `!` detach rules as `effectiveCspFor`, so a
 * route that adds a header must detach the inherited one or the browser sees
 * both and picks one.
 */
function effectiveHeaderFor(
  blocks: HeaderBlock[],
  path: string,
  header: string,
): string[] {
  let values: string[] = [];
  for (const block of blocks) {
    const matches =
      block.pattern === "/*" || path.startsWith(block.pattern.replace(/\*$/, ""));
    if (!matches) continue;
    for (const line of block.lines) {
      if (line.startsWith("! ")) {
        if (line.slice(2).trim() === header) values = [];
        continue;
      }
      const [name, ...rest] = line.split(":");
      if (name.trim() === header) values.push(rest.join(":").trim());
    }
  }
  return values;
}

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

  // The landing page's price tape reads the public market-data Worker, so the
  // strict connect-src must allow that origin or the browser blocks the fetch
  // and the band sits on its connecting line forever.
  it("allows the market-data origin in connect-src, env-overridable", () => {
    expect(resolveMarketDataOrigin({ NEXT_PUBLIC_MARKET_DATA_URL: "https://md.example/api/" })).toBe(
      "https://md.example",
    );
    expect(resolveMarketDataOrigin({})).toBeNull();
    expect(resolveMarketDataOrigin({ NEXT_PUBLIC_MARKET_DATA_URL: "not a url" })).toBeNull();

    expect(marketDataOriginForCsp({})).toBe(DEFAULT_MARKET_DATA_ORIGIN);
    expect(DEFAULT_MARKET_DATA_ORIGIN).toBe("https://graph.digithings.ai");
    expect(digithingsCsp(undefined, "https://md.example")).toContain(
      "connect-src 'self' https://api.github.com https://md.example",
    );
  });

  it("adds the Supabase origin to connect-src only when the env is set", () => {
    expect(resolveSupabaseOrigin({ NEXT_PUBLIC_SUPABASE_URL: "https://db.example/x/" })).toBe(
      "https://db.example",
    );
    expect(resolveSupabaseOrigin({})).toBeNull();
    expect(resolveSupabaseOrigin({ NEXT_PUBLIC_SUPABASE_URL: "not a url" })).toBeNull();

    // Unset means no extra source: the committed default policy is unchanged, so
    // the band's badged example series and the static export both still hold.
    expect(supabaseOriginForCsp({})).toBeNull();
    expect(digithingsCsp(undefined, "https://graph.digithings.ai", null)).not.toContain(
      "connect-src 'self' https://api.github.com https://graph.digithings.ai ",
    );
    expect(
      digithingsCsp(undefined, "https://graph.digithings.ai", "https://db.example"),
    ).toContain("connect-src 'self' https://api.github.com https://graph.digithings.ai https://db.example");
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

  it("drops Referrer-Policy to no-referrer on the OCC invite route only", () => {
    // The invite key rides in the /chat/occ query (DIG-1210). The /* policy
    // already strips query on cross-origin navigations, but a same-origin
    // request still sends the full URL — every first-party asset on the page
    // would see the key. Detach the inherited value first, or Cloudflare joins
    // both and the browser picks one.
    const blocks = parseHeaderBlocks(
      renderCloudflareHeaders(frameSrcForCsp()),
    );
    const occBlock = blocks.find((b) => b.pattern === "/chat/occ*");
    expect(occBlock?.lines).toContain("! Referrer-Policy");
    expect(occBlock?.lines).toContain("Referrer-Policy: no-referrer");

    expect(effectiveHeaderFor(blocks, "/chat/occ", "Referrer-Policy")).toEqual([
      "no-referrer",
    ]);
    // Splat, so the export's alternate URLs are covered too.
    expect(
      effectiveHeaderFor(blocks, "/chat/occ.html", "Referrer-Policy"),
    ).toEqual(["no-referrer"]);
    // Unrelated routes keep the site-wide policy.
    expect(effectiveHeaderFor(blocks, "/", "Referrer-Policy")).toEqual([
      "strict-origin-when-cross-origin",
    ]);
    expect(effectiveHeaderFor(blocks, "/chat", "Referrer-Policy")).toEqual([
      "strict-origin-when-cross-origin",
    ]);
  });

  it("committed _headers carries the OCC invite route referrer rule", () => {
    const blocks = parseHeaderBlocks(readFileSync(headersPath, "utf8"));
    expect(
      effectiveHeaderFor(blocks, "/chat/occ", "Referrer-Policy"),
    ).toEqual(["no-referrer"]);
  });

  it("leaves the CSP on the OCC invite route at the site-wide value", () => {
    // The referrer rule must not detach anything else, or the chat iframe
    // would lose its frame-src and stop rendering.
    const blocks = parseHeaderBlocks(readFileSync(headersPath, "utf8"));
    expect(effectiveCspFor(blocks, "/chat/occ")).toEqual([
      digithingsCsp(DEFAULT_DIGICHAT_EMBED_ORIGIN),
    ]);
  });
});
