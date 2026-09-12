/**
 * Copy committed OpenAPI snapshots into the static export tree and vendor
 * swagger-ui-dist assets (no CDN — CSP stays 'self').
 *
 * Specs: docs/openapi/*.json → public/openapi/
 * UI:    node_modules/swagger-ui-dist → public/swagger-ui/
 *
 * Localhost/private server URLs are stripped from public copies so the site
 * never advertises a private endpoint as the try-it target. Specs remain
 * committed under docs/openapi/ unchanged.
 */
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = join(root, "../..");
const srcDir = join(repoRoot, "docs/openapi");
const outDir = join(root, "public/openapi");
const swaggerOut = join(root, "public/swagger-ui");

const SWAGGER_FILES = [
  "swagger-ui.css",
  "swagger-ui-bundle.js",
  "swagger-ui-standalone-preset.js",
  "swagger-ui.css.map",
  "swagger-ui-bundle.js.map",
  "swagger-ui-standalone-preset.js.map",
];

function isPrivateServerUrl(url) {
  if (typeof url !== "string" || !url.trim()) return true;
  try {
    const u = new URL(url);
    const host = u.hostname.toLowerCase();
    return (
      host === "localhost" ||
      host === "127.0.0.1" ||
      host === "0.0.0.0" ||
      host === "::1" ||
      host.endsWith(".local") ||
      host.endsWith(".internal")
    );
  } catch {
    return true;
  }
}

function sanitizeSpec(raw) {
  const spec = JSON.parse(raw);
  if (Array.isArray(spec.servers)) {
    const publicServers = spec.servers.filter(
      (s) => s && typeof s.url === "string" && !isPrivateServerUrl(s.url),
    );
    if (publicServers.length === 0) {
      delete spec.servers;
    } else {
      spec.servers = publicServers;
    }
  }
  return `${JSON.stringify(spec, null, 2)}\n`;
}

if (!existsSync(srcDir)) {
  console.error(`ERROR: missing ${srcDir}`);
  process.exit(1);
}

mkdirSync(outDir, { recursive: true });
const jsonFiles = readdirSync(srcDir).filter((f) => f.endsWith(".json"));
if (jsonFiles.length === 0) {
  console.error(`ERROR: no OpenAPI JSON under ${srcDir}`);
  process.exit(1);
}

for (const name of jsonFiles) {
  const body = readFileSync(join(srcDir, name), "utf8");
  writeFileSync(join(outDir, name), sanitizeSpec(body), "utf8");
}
console.log(`wrote ${jsonFiles.length} OpenAPI specs → ${outDir}`);

const swaggerPkg = dirname(require.resolve("swagger-ui-dist/package.json"));
mkdirSync(swaggerOut, { recursive: true });
for (const name of SWAGGER_FILES) {
  const from = join(swaggerPkg, name);
  if (!existsSync(from)) continue;
  copyFileSync(from, join(swaggerOut, name));
}
console.log(`vendored swagger-ui assets → ${swaggerOut}`);
