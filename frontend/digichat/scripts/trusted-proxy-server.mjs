import { spawn } from "node:child_process";
import { existsSync, realpathSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const publicPort = Number(process.env.PORT ?? "3000");
const upstreamPort = Number(process.env.DIGICHAT_NEXT_INTERNAL_PORT ?? "3001");
const upstreamHost = "127.0.0.1";
const hopByHopHeaders = [
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
];

/**
 * Copy request headers while reserving x-digichat-peer-ip for this process.
 * The caller cannot choose that value: it is always overwritten with the TCP
 * peer address seen by the public listener.
 */
function withoutHopByHopHeaders(headers) {
  const forwarded = { ...headers };
  for (const name of hopByHopHeaders) {
    delete forwarded[name];
  }
  return forwarded;
}

export function forwardHeaders(headers, peerIp) {
  const forwarded = withoutHopByHopHeaders(headers);
  delete forwarded["x-digichat-peer-ip"];
  forwarded["x-digichat-peer-ip"] = peerIp;
  return forwarded;
}

function nextServerPath() {
  const candidates = [
    process.env.DIGICHAT_NEXT_SERVER_PATH,
    "frontend/digichat/server.js",
    ".next/standalone/frontend/digichat/server.js",
  ];
  const path = candidates.find((candidate) => candidate && existsSync(candidate));
  if (!path) throw new Error("Cannot locate digichat's Next standalone server.js.");
  return path;
}

function waitForNext() {
  return new Promise((resolveReady, rejectReady) => {
    const deadline = Date.now() + 30_000;
    const attempt = () => {
      const socket = net.connect(upstreamPort, upstreamHost);
      socket.once("connect", () => {
        socket.destroy();
        resolveReady();
      });
      socket.once("error", () => {
        socket.destroy();
        if (Date.now() >= deadline) {
          rejectReady(new Error("digichat's Next server did not become ready within 30 seconds."));
        } else {
          setTimeout(attempt, 100);
        }
      });
    };
    attempt();
  });
}

function start() {
  const capturePeer = Boolean(process.env.DIGICHAT_TRUSTED_PROXIES?.trim());
  const next = spawn(process.execPath, [nextServerPath()], {
    env: {
      ...process.env,
      HOSTNAME: capturePeer ? upstreamHost : process.env.HOSTNAME,
      PORT: String(capturePeer ? upstreamPort : publicPort),
    },
    stdio: "inherit",
  });

  next.on("exit", (code) => process.exit(code ?? 1));
  if (!capturePeer) return;

  const server = http.createServer((req, res) => {
    const peerIp = req.socket.remoteAddress ?? "";
    const upstream = http.request(
      {
        headers: forwardHeaders(req.headers, peerIp),
        host: upstreamHost,
        method: req.method,
        path: req.url,
        port: upstreamPort,
      },
      (upstreamResponse) => {
        res.writeHead(upstreamResponse.statusCode ?? 502, withoutHopByHopHeaders(upstreamResponse.headers));
        upstreamResponse.pipe(res);
      }
    );
    upstream.on("error", () => {
      if (!res.headersSent) res.writeHead(502);
      res.destroy();
    });
    req.pipe(upstream);
  });

  waitForNext()
    .then(() => server.listen(publicPort, process.env.HOSTNAME || undefined))
    .catch((error) => {
      console.error(error);
      next.kill("SIGTERM");
      process.exitCode = 1;
    });
}

const entrypoint = process.argv[1] && pathToFileURL(realpathSync(resolve(process.argv[1]))).href;
if (import.meta.url === entrypoint) start();
