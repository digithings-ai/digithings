import { readFileSync } from "node:fs";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { describe, expect, it } from "vitest";
import {
  forwardHeaders,
  proxyToUpstream,
  resolveDigichatVersion,
} from "../../scripts/trusted-proxy-server.mjs";

function listen(server: http.Server): Promise<number> {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address() as AddressInfo;
      resolve(address.port);
    });
  });
}

function closeServer(server: http.Server): Promise<void> {
  return new Promise((resolve) => {
    server.close(() => resolve());
  });
}

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

  it("strips a caller-supplied peer and stamp, then writes the socket and our stamp", () => {
    const headers = forwardHeaders(
      {
        "x-digichat-peer-ip": "198.51.100.1",
        "x-digichat-peer-stamp": "caller-chose-this",
        "cf-connecting-ip": "203.0.113.5",
      },
      "10.0.0.7",
      "server-stamp",
    );
    expect(headers["x-digichat-peer-ip"]).toBe("10.0.0.7");
    expect(headers["x-digichat-peer-stamp"]).toBe("server-stamp");
    expect(headers["cf-connecting-ip"]).toBe("203.0.113.5");
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

  it("returns a finished upstream body", async () => {
    const upstream = http.createServer((_req, res) => {
      res.end("ok");
    });
    const upstreamPort = await listen(upstream);
    const proxy = http.createServer((req, res) => {
      proxyToUpstream(req, res, {
        headers: forwardHeaders(req.headers, "127.0.0.1", "stamp"),
        host: "127.0.0.1",
        path: req.url ?? "/",
        port: upstreamPort,
      });
    });
    const proxyPort = await listen(proxy);
    try {
      const body = await new Promise<string>((resolve, reject) => {
        http
          .get({ host: "127.0.0.1", port: proxyPort, path: "/" }, (res) => {
            const chunks: Buffer[] = [];
            res.on("data", (chunk: Buffer) => chunks.push(chunk));
            res.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
          })
          .on("error", reject);
      });
      expect(body).toBe("ok");
    } finally {
      await closeServer(proxy);
      await closeServer(upstream);
    }
  });

  it("destroys the upstream request when the client aborts", async () => {
    let upstreamClosedEarly = false;
    let markOpen: () => void = () => {};
    let markClosed: () => void = () => {};
    const opened = new Promise<void>((resolve) => {
      markOpen = resolve;
    });
    const closed = new Promise<void>((resolve) => {
      markClosed = resolve;
    });
    const upstream = http.createServer((req, upRes) => {
      markOpen();
      req.on("close", () => {
        if (!upRes.writableFinished) {
          upstreamClosedEarly = true;
          markClosed();
        }
      });
    });
    const upstreamPort = await listen(upstream);
    const proxy = http.createServer((req, res) => {
      proxyToUpstream(req, res, {
        headers: forwardHeaders(req.headers, "127.0.0.1", "stamp"),
        host: "127.0.0.1",
        path: req.url ?? "/",
        port: upstreamPort,
      });
    });
    const proxyPort = await listen(proxy);
    try {
      const client = http.request({
        host: "127.0.0.1",
        method: "POST",
        path: "/api/chat",
        port: proxyPort,
      });
      client.on("error", () => {});
      client.end("{}");
      await opened;
      client.destroy();
      await Promise.race([
        closed,
        new Promise((_, reject) => {
          setTimeout(() => reject(new Error("upstream request stayed open after client abort")), 1000);
        }),
      ]);
      expect(upstreamClosedEarly).toBe(true);
    } finally {
      await closeServer(proxy);
      await closeServer(upstream);
    }
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
