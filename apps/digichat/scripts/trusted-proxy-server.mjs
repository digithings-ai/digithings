import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, realpathSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import { resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const publicPort = Number(process.env.PORT ?? "3000");
const upstreamPort = Number(process.env.DIGICHAT_NEXT_INTERNAL_PORT ?? "3001");
const upstreamHost = "127.0.0.1";
// Read-only OCC helpdesk MCP (scripts/zammad_mcp): a second loopback listener
// inside this image, reached only through the public listener below.
const zammadPort = Number(process.env.ZAMMAD_MCP_PORT ?? "8770");
const zammadPrefix = "/api/mcp/zammad";
// Container/repo root: this script lives at <root>/apps/digichat/scripts/, and
// `python3 -m scripts.zammad_mcp.server` needs the root on its path.
const appRoot = fileURLToPath(new URL("../../..", import.meta.url));
// Cap for the zammad-mcp restart backoff, and the uptime below which a run
// counts as a crash rather than an ordinary exit.
const zammadRestartCapMs = 30_000;
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
 * Same sentence as TRUSTED_PROXIES_UNSET_WARNING in embed-ip-rate-limit.ts.
 * The mjs entrypoint cannot import that module.
 */
export const trustedProxiesUnsetWarning =
  "DIGICHAT_TRUSTED_PROXIES is unset. The entrypoint stamps the socket peer. Guardrail and premium keys use that socket when it is the client, and unknown when it is a shared ingress. The embed limiter and trial quota follow develop: cf-connecting-ip, then the leftmost X-Forwarded-For hop, otherwise unknown. A header-less request is unknown: the embed limiter collapses onto embed_ip:unknown, and the trial quota skips it. Set DIGICHAT_TRUSTED_PROXIES to the container ingress or overlay peer the entrypoint logs, never Cloudflare's edge ranges. Spoofable headers are not guardrail or premium keys.";

/**
 * Copy request headers while reserving the peer headers for this process.
 * The caller cannot choose those values: both are deleted, then the TCP
 * peer and this process's stamp are written.
 */
function withoutHopByHopHeaders(headers) {
  const forwarded = { ...headers };
  for (const name of hopByHopHeaders) {
    delete forwarded[name];
  }
  return forwarded;
}

export function forwardHeaders(headers, peerIp, stamp = process.env.DIGICHAT_PEER_STAMP) {
  const forwarded = withoutHopByHopHeaders(headers);
  delete forwarded["x-digichat-peer-ip"];
  delete forwarded["x-digichat-peer-stamp"];
  forwarded["x-digichat-peer-ip"] = peerIp;
  if (typeof stamp === "string" && stamp.trim()) {
    forwarded["x-digichat-peer-stamp"] = stamp.trim();
  }
  return forwarded;
}

function ensurePeerStamp() {
  if (!process.env.DIGICHAT_PEER_STAMP?.trim()) {
    process.env.DIGICHAT_PEER_STAMP = randomBytes(16).toString("hex");
  }
}

const PACKAGE_JSON_BESIDE_SCRIPT = fileURLToPath(new URL("../package.json", import.meta.url));

/**
 * DIGICHAT_VERSION for GET /api/health. Prefer a non-empty env (compose/override),
 * then the image-baked /etc/digichat-version, then this package's package.json.
 */
export function resolveDigichatVersion(env = process.env) {
  const fromEnv = typeof env.DIGICHAT_VERSION === "string" ? env.DIGICHAT_VERSION.trim() : "";
  if (fromEnv) return fromEnv;
  const files = ["/etc/digichat-version", PACKAGE_JSON_BESIDE_SCRIPT];
  for (const path of files) {
    if (!existsSync(path)) continue;
    try {
      const raw = readFileSync(path, "utf8").trim();
      if (path.endsWith("package.json")) {
        const version = JSON.parse(raw).version;
        if (typeof version === "string" && version.trim()) return version.trim();
      } else if (raw) {
        return raw;
      }
    } catch {
      // try the next candidate
    }
  }
  return "";
}

function nextServerPath() {
  const candidates = [
    process.env.DIGICHAT_NEXT_SERVER_PATH,
    "apps/digichat/server.js",
    ".next/standalone/apps/digichat/server.js",
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

/**
 * Start the in-image zammad-mcp only when a token is configured — the digichat
 * image must boot without one. Restarts use a bounded exponential backoff so a
 * crash loop stays quiet instead of storming. stdio is inherited so the MCP
 * server's own logs land in the container log.
 */
function startZammadMcp() {
  if (!process.env.ZAMMAD_API_TOKEN?.trim()) return;
  let failures = 0;
  const launch = () => {
    const startedAt = Date.now();
    console.log(
      `[zammad-mcp] starting: python3 -m scripts.zammad_mcp.server --port ${zammadPort}`,
    );
    const child = spawn(
      "python3",
      ["-m", "scripts.zammad_mcp.server", "--port", String(zammadPort)],
      {
        cwd: appRoot,
        env: { ...process.env, ZAMMAD_MCP_HOST: "0.0.0.0" },
        stdio: "inherit",
      },
    );
    child.on("exit", (code, signal) => {
      // A run that stayed up long enough is not a crash loop: reset the backoff.
      if (Date.now() - startedAt >= zammadRestartCapMs) failures = 0;
      const delay = Math.min(zammadRestartCapMs, 1_000 * 2 ** Math.min(failures, 5));
      failures += 1;
      console.log(
        `[zammad-mcp] exited code=${code ?? "null"} signal=${signal ?? "null"}; restarting in ${delay}ms`,
      );
      setTimeout(launch, delay);
    });
  };
  launch();
}

function start() {
  ensurePeerStamp();
  const bakedVersion = resolveDigichatVersion();
  if (bakedVersion) process.env.DIGICHAT_VERSION = bakedVersion;
  if (!process.env.DIGICHAT_TRUSTED_PROXIES?.trim()) {
    console.warn(trustedProxiesUnsetWarning);
  }
  const next = spawn(process.execPath, [nextServerPath()], {
    env: {
      ...process.env,
      HOSTNAME: upstreamHost,
      PORT: String(upstreamPort),
    },
    stdio: "inherit",
  });

  next.on("exit", (code) => process.exit(code ?? 1));
  startZammadMcp();

  let loggedPeer = false;
  const server = http.createServer((req, res) => {
    const peerIp = req.socket.remoteAddress ?? "";
    if (!loggedPeer && peerIp && !process.env.DIGICHAT_TRUSTED_PROXIES?.trim()) {
      loggedPeer = true;
      console.warn(
        `DIGICHAT_TRUSTED_PROXIES is unset. First socket peer is ${peerIp}. Set DIGICHAT_TRUSTED_PROXIES to that container ingress or overlay address, never Cloudflare's edge ranges.`,
      );
    }
    // /api/mcp/zammad* is served by the in-image zammad-mcp, not Next: keep the
    // method/headers/body and rewrite the path to the MCP endpoint.
    const isZammadMcp = (req.url ?? "").startsWith(zammadPrefix);
    const upstream = http.request(
      {
        headers: forwardHeaders(req.headers, peerIp),
        host: upstreamHost,
        method: req.method,
        path: isZammadMcp ? "/mcp" : req.url,
        port: isZammadMcp ? zammadPort : upstreamPort,
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
