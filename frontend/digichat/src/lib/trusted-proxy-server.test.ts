import { describe, expect, it } from "vitest";
import { forwardHeaders } from "../../scripts/trusted-proxy-server.mjs";

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
