import { describe, expect, it } from "vitest";
import {
  resolveEmbedRenderToken,
  stripEmbedTokenFromUrl,
} from "./embed-token-transport";

describe("resolveEmbedRenderToken", () => {
  it("prefers the proxy-forwarded header over the query param", () => {
    expect(
      resolveEmbedRenderToken({
        headerToken: "header-secret",
        queryToken: "query-secret",
      }),
    ).toBe("header-secret");
  });

  it("falls back to the query param when no header is present", () => {
    expect(resolveEmbedRenderToken({ queryToken: "query-secret" })).toBe(
      "query-secret",
    );
    expect(
      resolveEmbedRenderToken({ headerToken: null, queryToken: "q" }),
    ).toBe("q");
  });

  it("resolves array query values first-wins", () => {
    expect(resolveEmbedRenderToken({ queryToken: ["a", "b"] })).toBe("a");
  });

  it("treats empty and whitespace-only values as absent on both arms", () => {
    expect(
      resolveEmbedRenderToken({ headerToken: "  ", queryToken: "q" }),
    ).toBe("q");
    expect(resolveEmbedRenderToken({ queryToken: "   " })).toBeUndefined();
    expect(resolveEmbedRenderToken({})).toBeUndefined();
  });
});

describe("stripEmbedTokenFromUrl", () => {
  it("removes token and keeps every other param", () => {
    const { token, cleanUrl } = stripEmbedTokenFromUrl(
      "http://127.0.0.1:3000/embed?token=SECRET&host=client.example.com&theme=light",
    );
    expect(token).toBe("SECRET");
    const clean = new URL(cleanUrl);
    expect(clean.pathname).toBe("/embed");
    expect(clean.searchParams.get("token")).toBeNull();
    expect(clean.searchParams.get("host")).toBe("client.example.com");
    expect(clean.searchParams.get("theme")).toBe("light");
  });

  it("keeps mode=embed and strips token on the canonical route", () => {
    const { token, cleanUrl } = stripEmbedTokenFromUrl(
      "http://127.0.0.1:3000/?mode=embed&token=SECRET",
    );
    expect(token).toBe("SECRET");
    expect(cleanUrl).toContain("mode=embed");
    expect(cleanUrl).not.toContain("SECRET");
  });

  it("returns the URL unchanged and no token when absent", () => {
    const raw = "http://127.0.0.1:3000/embed?host=client.example.com";
    const { token, cleanUrl } = stripEmbedTokenFromUrl(raw);
    expect(token).toBeUndefined();
    expect(cleanUrl).toBe(raw);
  });

  it("strips an empty token with no token resolved", () => {
    const { token, cleanUrl } = stripEmbedTokenFromUrl(
      "http://127.0.0.1:3000/embed?token=&host=h",
    );
    expect(token).toBeUndefined();
    expect(new URL(cleanUrl).searchParams.has("token")).toBe(false);
  });
});
