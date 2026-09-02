import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_DIGICHAT_EMBED_ORIGIN,
  digithingsCsp,
  embedOriginForChat,
  frameSrcForCsp,
  renderCloudflareHeaders,
  resolveDigichatEmbedOrigin,
} from "./security-headers.mjs";

const headersPath = resolve(__dirname, "../public/_headers");

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
});
