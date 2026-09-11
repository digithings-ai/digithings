import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { forwardHeaders, resolveDigichatVersion } from "../../scripts/trusted-proxy-server.mjs";

const packageVersion = JSON.parse(
  readFileSync(new URL("../../package.json", import.meta.url), "utf8")
).version;

describe("trusted-proxy server", () => {
  it("replaces a caller-supplied internal peer header with the socket peer", () => {
    const headers = forwardHeaders(
      {
        "cf-connecting-ip": "198.51.100.1",
        "x-digichat-peer-ip": "203.0.113.99",
      },
      "::ffff:10.0.0.7"
    );

    expect(headers["x-digichat-peer-ip"]).toBe("::ffff:10.0.0.7");
    expect(headers["cf-connecting-ip"]).toBe("198.51.100.1");
  });

  it("does not forward hop-by-hop headers to the loopback server", () => {
    const headers = forwardHeaders(
      {
        connection: "keep-alive",
        "keep-alive": "timeout=5",
        "transfer-encoding": "chunked",
        upgrade: "websocket",
        "x-forwarded-for": "198.51.100.1",
      },
      "10.0.0.7"
    );

    expect(headers).not.toHaveProperty("connection");
    expect(headers).not.toHaveProperty("keep-alive");
    expect(headers).not.toHaveProperty("transfer-encoding");
    expect(headers).not.toHaveProperty("upgrade");
    expect(headers["x-forwarded-for"]).toBe("198.51.100.1");
  });
});

describe("resolveDigichatVersion", () => {
  it("prefers a non-empty DIGICHAT_VERSION env", () => {
    expect(
      resolveDigichatVersion({ DIGICHAT_VERSION: " 9.9.9 ", NODE_ENV: "test" }),
    ).toBe("9.9.9");
  });

  it("falls back to this package's version when env is blank", () => {
    expect(resolveDigichatVersion({ DIGICHAT_VERSION: "", NODE_ENV: "test" })).toBe(
      packageVersion,
    );
    expect(packageVersion).not.toBe("0.1.0");
  });
});
