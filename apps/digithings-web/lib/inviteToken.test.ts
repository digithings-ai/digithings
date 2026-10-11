import { describe, expect, it } from "vitest";
import { INVITE_TOKEN_PARAM, readInviteToken } from "./inviteToken";

describe("readInviteToken", () => {
  it("uses the same key digichat already enforces", () => {
    // One secret, one name. A second query key for the same token would be a
    // support burden and an operator-error surface, so the invite URL and the
    // embed URL share `token`.
    expect(INVITE_TOKEN_PARAM).toBe("token");
  });

  it("reads the key off the parent URL query", () => {
    expect(readInviteToken("?token=abc123")).toBe("abc123");
  });

  it("reads it from a query with other parameters around it", () => {
    expect(readInviteToken("?utm_source=email&token=abc123&x=1")).toBe("abc123");
  });

  it("returns undefined when the invite carries no key", () => {
    expect(readInviteToken(undefined)).toBeUndefined();
    expect(readInviteToken("")).toBeUndefined();
    expect(readInviteToken("?")).toBeUndefined();
    expect(readInviteToken("?utm_source=email")).toBeUndefined();
  });

  it("never returns an empty token, so no bare token= is forwarded", () => {
    // `?token=` is present-but-empty: forwarding it would tell digichat an
    // invite was attempted while authorizing nothing.
    expect(readInviteToken("?token=")).toBeUndefined();
    expect(readInviteToken("?token=%20%20")).toBeUndefined();
  });

  it("trims surrounding whitespace rather than sending it as part of the key", () => {
    expect(readInviteToken("?token=%20abc123%20")).toBe("abc123");
  });

  it("decodes percent-encoding exactly as digichat's own read will", () => {
    // digichat reads the key with `searchParams.get("token")` in embed-client.tsx,
    // which percent-decodes too. Decoding here is therefore not a leak of a
    // mismatch: both ends of the hop apply the same form decoding, so the value
    // compared against the tenant registry is the one the link minted.
    expect(readInviteToken("?token=a%2Bb%3Dc%3D")).toBe("a+b=c=");
  });

  it("round-trips back to the same bytes through the embed URL", () => {
    // The value we read is re-encoded by `searchParams.set` on the iframe src and
    // decoded again by digichat. Both hops use URLSearchParams, so the round trip
    // is the identity — this is the property that actually matters, and it is
    // what a naive "don't touch the value" reading would have broken.
    const minted = "a+b/c=d&e";
    const link = `?token=${encodeURIComponent(minted)}`;
    const read = readInviteToken(link);
    expect(read).toBe(minted);
    const forwarded = new URL("https://digithings.ai/embed");
    if (read) forwarded.searchParams.set("token", read);
    expect(new URLSearchParams(forwarded.search).get("token")).toBe(minted);
  });

  it("documents that a bare + in a token is a space, so minters must not use it", () => {
    // Query strings are form-encoded: `+` means space. A token minted from an
    // alphabet containing `+` and pasted into a link unescaped would arrive as a
    // space and fail the registry comparison. Mint from a URL-safe alphabet, or
    // percent-encode the key when composing the link.
    expect(readInviteToken("?token=a+b")).toBe("a b");
    expect(readInviteToken("?token=a+b")).not.toBe("a+b");
    expect(readInviteToken("?token=a%2Bb")).toBe("a+b");
  });

  it("takes the first occurrence when the key is repeated", () => {
    expect(readInviteToken("?token=first&token=second")).toBe("first");
  });

  it("does not match a key that only appears as a substring of another name", () => {
    expect(readInviteToken("?xtoken=abc123")).toBeUndefined();
    expect(readInviteToken("?token2=abc123")).toBeUndefined();
  });

  it("is not confused by a token-looking value in the fragment", () => {
    // The fragment is never sent to a server and is not part of location.search.
    expect(readInviteToken("?utm=1#token=abc123")).toBeUndefined();
  });
});
