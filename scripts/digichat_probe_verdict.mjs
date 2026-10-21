#!/usr/bin/env node
/**
 * digichat_probe_verdict.mjs — the one place that decides whether a booted
 * digichat image is fit to publish.
 *
 * Both publish lanes call this file:
 *   - .github/workflows/publish-digichat-image.yml (the GitHub lane)
 *   - scripts/local-deploy/publish_image.sh (the local rehearsal)
 *
 * The rules are here and nowhere else, because the two lanes used to keep
 * their own copy and drifted: the local lane never read the status code the
 * CI lane read, so a rehearsal passed where the release failed.
 *
 * Usage:  printf '%s' "$body" | node scripts/digichat_probe_verdict.mjs \
 *             --status <code> --version <built version>
 *
 * Exit 0 and one line on stdout when the image may be published:
 *   OK version=<v> status=<code> tolerated=<key=value,...|none>
 * Exit 1 and one line on stdout when it may not:
 *   REFUSE <reason>
 *
 * No dependencies — plain Node ESM.
 */
import { readFileSync } from "node:fs";

// The four services a standalone container cannot reach. Only a fetch that
// never completed ("unreachable") is tolerated for them; the health route
// records an upstream that ANSWERED with a non-2xx as "http_<status>", and
// that is a real fault, not the degradation this probe exists to allow.
const ECOSYSTEM = ["digraph", "digiquant", "digitrace", "digisearch"];

function parseArgs(argv) {
  const args = { status: "", version: "" };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (key === "--status") args.status = String(argv[i + 1] ?? "");
    else if (key === "--version") args.version = String(argv[i + 1] ?? "");
    else {
      process.stdout.write(`REFUSE unknown argument '${key}'\n`);
      process.exit(1);
    }
    i += 1;
  }
  return args;
}

function refuse(reason) {
  process.stdout.write(`REFUSE ${reason}\n`);
  process.exit(1);
}

const { status, version } = parseArgs(process.argv.slice(2));

if (status !== "200" && status !== "503") {
  refuse(`/api/health answered '${status}', not 200 or 503`);
}

let raw = "";
try {
  raw = readFileSync(0, "utf8");
} catch {
  raw = "";
}
if (raw.trim() === "") {
  refuse(`/api/health answered '${status}' with no body — the route did not answer`);
}

let body = null;
try {
  body = JSON.parse(raw);
} catch {
  body = null;
}
if (body === null || typeof body !== "object" || Array.isArray(body)) {
  refuse(`/api/health answered '${status}' with a body that is not the health route's JSON`);
}
if (body.version === undefined || body.version === null) {
  refuse(`/api/health answered '${status}' with JSON that carries no version`);
}
if (String(body.version) !== version) {
  refuse(`/api/health reports version '${body.version}', but this image was built as '${version}'`);
}

const checks =
  body.checks && typeof body.checks === "object" && !Array.isArray(body.checks) ? body.checks : {};
const asText = (value) => (value === undefined || value === null ? "missing" : String(value));

const service = asText(checks.service);
const database = asText(checks.database);
const tolerated = [];
const unexpected = [];
if (service !== "ok") unexpected.push(`service=${service}`);
if (database !== "ok" && database !== "skipped") unexpected.push(`database=${database}`);
for (const [key, value] of Object.entries(checks)) {
  if (key === "service" || key === "database") continue;
  const text = asText(value);
  if (text === "ok" || text === "skipped") continue;
  if (ECOSYSTEM.includes(key) && text === "unreachable") {
    tolerated.push(`${key}=${text}`);
    continue;
  }
  unexpected.push(`${key}=${text}`);
}
if (unexpected.length > 0) {
  refuse(
    `/api/health answered '${status}' with checks that are not only the unreachable ecosystem ` +
      `services (service: ${service}, database: ${database}, unexpected: ${unexpected.join(", ")})`,
  );
}

process.stdout.write(
  `OK version=${body.version} status=${status} tolerated=${tolerated.length > 0 ? tolerated.join(",") : "none"}\n`,
);
