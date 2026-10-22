import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { CONTAINER_BASE_PATH, containerPathFor } from "./paths";

/**
 * The /chat cutover contract (DIG-5121).
 *
 * digithings.ai/chat is the canonical digichat surface (ADR 0018, GitHub
 * #1252). Three things have to agree for it to work, and each one can drift
 * on its own, so each is pinned here:
 *
 *   1. the EDGE claims the path — the digichat Worker declares
 *      `digithings.ai/chat*` (without the route the path never reaches the
 *      Worker and Pages keeps answering it);
 *   2. the IMAGE is built with the base path — Next bakes `basePath` at build
 *      time, so the Dockerfile has to carry the same value the Worker maps to;
 *   3. the APP is served under that base path without doubling — the app's
 *      chat surface is the ROOT route, so the base path plus the route is
 *      /chat, never /chat/chat.
 *
 * The compatibility routes (the legacy /embed*, /api/chat*, /api/embed*,
 * /api/byok*, /api/plan-proof*, /api/health and /_dtchat* paths) stay
 * declared for the ADR 0018 window, so this file also pins that they are
 * still there: removing them is a deliberate, separate change.
 */
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../..");

const DIGICHAT_WORKER = "apps/digichat-cloudflare/wrangler.toml";
const BASE_PLATFORM = "apps/digithings-stack-cloudflare/wrangler.toml";
const IMAGE = "infra/docker/Dockerfile.digichat-cloudflare";
const APP_DIR = "apps/digichat";
const WORKER_SRC = "apps/digichat-cloudflare/src";

const read = (relative: string): string =>
  readFileSync(join(repoRoot, relative), "utf8");

/**
 * The route patterns a wrangler.toml actually declares.
 *
 * Comments are stripped first and only the `[[routes]]` tables are read, so a
 * commented-out block (or a pattern mentioned in prose) cannot satisfy a pin:
 * the pattern has to sit in a real route table to be counted.
 */
function routePatterns(toml: string): string[] {
  const withoutComments = toml
    .split("\n")
    .map((line) => line.replace(/#.*$/, ""))
    .join("\n");
  return withoutComments
    .split(/\[\[routes\]\]/)
    .slice(1)
    .map((block) => block.match(/pattern\s*=\s*"([^"]+)"/)?.[1])
    .filter((pattern): pattern is string => Boolean(pattern));
}

/**
 * One Docker stage (the chunk between two FROMs) that carries `marker`.
 */
function dockerStage(image: string, marker: string): string {
  const stages = image.split(/(?=^FROM )/m);
  return stages.find((stage) => stage.includes(marker)) ?? "";
}

/** The canonical route pattern: the `*` form claims the bare /chat too. */
const CHAT_PATTERN = "digithings.ai/chat*";

/** The invite-gated OCC shell keeps its own, more specific pattern. */
const OCC_PATTERN = "digithings.ai/chat/occ*";

/**
 * The compatibility routes the ADR 0018 window keeps alive. Each one is a
 * full pattern, so the bare /api/health route is pinned exactly (not as a
 * prefix of something else).
 */
const COMPATIBILITY_PATTERNS = [
  "digithings.ai/embed*",
  "digithings.ai/api/chat*",
  "digithings.ai/api/embed*",
  "digithings.ai/api/byok*",
  "digithings.ai/api/plan-proof*",
  "digithings.ai/api/health",
  "digithings.ai/_dtchat*",
];

/**
 * The Worker's own routes, served by the Worker itself and never proxied.
 * They are pinned here too: the meta route is how a deploy is verified
 * (apps/digichat-cloudflare/scripts/deploy.mjs reads it back), and the admin
 * and MCP patterns are the secret-gated levers. Dropping any of them would
 * take a live capability with it.
 */
const WORKER_OWNED_PATTERNS = [
  "digithings.ai/_digichat/meta",
  "digithings.ai/_digichat-admin*",
  "digithings.ai/api/mcp/zammad*",
];

describe("the /chat cutover (DIG-5121)", () => {
  it("the base path is the canonical /chat", () => {
    expect(CONTAINER_BASE_PATH).toBe("/chat");
  });

  it(`${DIGICHAT_WORKER} claims digithings.ai/chat*`, () => {
    expect(routePatterns(read(DIGICHAT_WORKER))).toContain(CHAT_PATTERN);
  });

  it(`${DIGICHAT_WORKER} keeps the invite-gated OCC shell on its own pattern`, () => {
    expect(routePatterns(read(DIGICHAT_WORKER))).toContain(OCC_PATTERN);
  });

  it(`${BASE_PLATFORM} claims no digithings.ai path — the app belongs to the digichat Worker`, () => {
    const stack = routePatterns(read(BASE_PLATFORM));
    // No route pattern on the apex zone: the stack serves graph/key/search
    // subdomains only, and every digithings.ai digichat path is owned by the
    // digichat Worker (Chris, 2026-10-19).
    expect(stack.filter((pattern) => pattern.startsWith("digithings.ai/"))).toEqual([]);
    expect(stack).not.toContain(CHAT_PATTERN);
    expect(stack).not.toContain(OCC_PATTERN);
  });

  it("the compatibility routes stay declared for the ADR 0018 window", () => {
    const patterns = routePatterns(read(DIGICHAT_WORKER));
    for (const pattern of COMPATIBILITY_PATTERNS) {
      expect(patterns).toContain(pattern);
    }
  });

  it("the Worker's own routes stay declared (meta read-back, admin lever, MCP)", () => {
    const patterns = routePatterns(read(DIGICHAT_WORKER));
    for (const pattern of WORKER_OWNED_PATTERNS) {
      expect(patterns).toContain(pattern);
    }
  });

  it("the image is built with the same base path the Worker maps to", () => {
    const image = read(IMAGE);
    const baked = image.match(/ARG DIGICHAT_BASE_PATH="([^"]+)"/)?.[1];
    expect(baked).toBe(CONTAINER_BASE_PATH);
    // The public var is derived from the same ARG, so the server's base path
    // and the client's prefix cannot drift apart.
    expect(image).toMatch(/ENV NEXT_PUBLIC_DIGICHAT_BASE_PATH=\$DIGICHAT_BASE_PATH/);
    // And the app reads exactly those two names — as code, not in a comment.
    expect(read(`${APP_DIR}/next.config.ts`)).toMatch(
      /basePath:\s*process\.env\.DIGICHAT_BASE_PATH/,
    );
    expect(read(`${APP_DIR}/src/lib/base-path.ts`)).toMatch(
      /process\.env\.NEXT_PUBLIC_DIGICHAT_BASE_PATH/,
    );
  });

  it("the base path is BAKED into the image, not just defaulted", () => {
    // The global ARG's default alone is not enough: it is the builder stage
    // that has to carry the value into `next build`, because Next bakes
    // `basePath` at build time. Without the builder-stage ENV the image is
    // built without a base path, the app answers at "/", and the Worker
    // (which asks for "/chat") gets nothing.
    const image = read(IMAGE);
    const builderStage = dockerStage(image, "npm run build");
    expect(builderStage).toMatch(/ARG DIGICHAT_BASE_PATH/);
    expect(builderStage).toMatch(/ENV DIGICHAT_BASE_PATH=\$DIGICHAT_BASE_PATH/);
    expect(builderStage).toMatch(/ENV NEXT_PUBLIC_DIGICHAT_BASE_PATH=\$DIGICHAT_BASE_PATH/);
    // The ENV has to be set BEFORE the build that reads it.
    const envAt = builderStage.indexOf("ENV DIGICHAT_BASE_PATH=");
    const buildAt = builderStage.indexOf("npm run build");
    expect(envAt).toBeGreaterThan(-1);
    expect(buildAt).toBeGreaterThan(-1);
    expect(envAt).toBeLessThan(buildAt);
  });

  it("the served path is not doubled: the app's chat surface is the root route", () => {
    // The app uses route groups, so a /chat page could hide inside one of
    // them: no route root may carry a "chat" segment.
    //
    // Only the ROUTE roots count — src/app itself and the route groups.
    // src/app/api/chat is not one of them: it is the API route /api/chat,
    // which the base path moves to /chat/api/chat (that is the point of the
    // compatibility mapping), not a second /chat.
    const appDir = join(repoRoot, APP_DIR, "src/app");
    const routeRoots = [appDir];
    for (const entry of readdirSync(appDir, { withFileTypes: true })) {
      if (entry.isDirectory() && entry.name.startsWith("(")) {
        routeRoots.push(join(appDir, entry.name));
      }
    }
    for (const root of routeRoots) {
      expect(existsSync(join(root, "chat"))).toBe(false);
    }
    // The app's single page route is the root of its group → the served path
    // is the base path itself.
    expect(existsSync(join(appDir, "(digichat)/page.tsx"))).toBe(true);
    expect(containerPathFor(CONTAINER_BASE_PATH)).toBe(CONTAINER_BASE_PATH);
    expect(containerPathFor(CONTAINER_BASE_PATH)).not.toBe(`${CONTAINER_BASE_PATH}${CONTAINER_BASE_PATH}`);
  });

  it("the Worker asks the container for the mapped path", () => {
    // The proxy is where the base path lands: the request the container sees
    // carries the path `containerPathFor` produces.
    const index = read(`${WORKER_SRC}/index.ts`);
    expect(index).toMatch(/const containerRequest = withContainerPath\(request, url\.pathname\);/);
    // …and it is the request that is actually fetched, not the original one.
    expect(index).toMatch(
      /await fetchContainerWithRetry\(containerRequest, \(req\) => container\.fetch\(req\)\)/,
    );
    expect(index).toMatch(/return frameSafeErrorResponse\(\s*containerRequest,/);
    // The rewrite itself lives with the path table it uses.
    const paths = read(`${WORKER_SRC}/paths.ts`);
    expect(paths).toMatch(/target\.pathname = containerPathFor\(pathname\)/);
  });
});
