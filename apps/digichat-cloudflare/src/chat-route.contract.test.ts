import { existsSync, readFileSync } from "node:fs";
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

const read = (relative: string): string =>
  readFileSync(join(repoRoot, relative), "utf8");

/** The canonical route pattern: the `*` form claims the bare /chat too. */
const CHAT_PATTERN = /pattern\s*=\s*"digithings\.ai\/chat\*"/;

/** The invite-gated OCC shell keeps its own, more specific pattern. */
const OCC_PATTERN = /pattern\s*=\s*"digithings\.ai\/chat\/occ\*"/;

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

describe("the /chat cutover (DIG-5121)", () => {
  it(`${DIGICHAT_WORKER} claims digithings.ai/chat*`, () => {
    expect(read(DIGICHAT_WORKER)).toMatch(CHAT_PATTERN);
  });

  it(`${DIGICHAT_WORKER} keeps the invite-gated OCC shell on its own pattern`, () => {
    expect(read(DIGICHAT_WORKER)).toMatch(OCC_PATTERN);
  });

  it(`${BASE_PLATFORM} claims no digithings.ai path — the app belongs to the digichat Worker`, () => {
    const stack = read(BASE_PLATFORM);
    // No route pattern on the apex zone: the stack serves graph/key/search
    // subdomains only, and every digithings.ai digichat path is owned by the
    // digichat Worker (Chris, 2026-10-19).
    expect(stack).not.toMatch(/pattern\s*=\s*"digithings\.ai\//);
    expect(stack).not.toMatch(CHAT_PATTERN);
    expect(stack).not.toMatch(OCC_PATTERN);
  });

  it("the compatibility routes stay declared for the ADR 0018 window", () => {
    const worker = read(DIGICHAT_WORKER);
    for (const pattern of COMPATIBILITY_PATTERNS) {
      expect(worker).toContain(`pattern = "${pattern}"`);
    }
  });

  it("the image is built with the same base path the Worker maps to", () => {
    const image = read(IMAGE);
    const baked = image.match(/ARG DIGICHAT_BASE_PATH="([^"]+)"/)?.[1];
    expect(baked).toBe(CONTAINER_BASE_PATH);
    // The public var is derived from the same ARG, so the server's base path
    // and the client's prefix cannot drift apart.
    expect(image).toMatch(/ENV NEXT_PUBLIC_DIGICHAT_BASE_PATH=\$DIGICHAT_BASE_PATH/);
    // And the app reads exactly those two names.
    expect(read(`${APP_DIR}/next.config.ts`)).toContain("DIGICHAT_BASE_PATH");
    expect(read(`${APP_DIR}/src/lib/base-path.ts`)).toContain("NEXT_PUBLIC_DIGICHAT_BASE_PATH");
  });

  it("the served path is not doubled: the app's chat surface is the root route", () => {
    // There is no /chat route directory, so the base path and the route do
    // not stack into /chat/chat. A future src/app/chat/page.tsx would.
    expect(existsSync(join(repoRoot, APP_DIR, "src/app/chat"))).toBe(false);
    expect(existsSync(join(repoRoot, APP_DIR, "src/app/(digichat)/page.tsx"))).toBe(true);
    // The path the Container is asked for is the base path itself.
    expect(containerPathFor(CONTAINER_BASE_PATH)).toBe(CONTAINER_BASE_PATH);
    expect(containerPathFor(CONTAINER_BASE_PATH)).not.toBe(`${CONTAINER_BASE_PATH}${CONTAINER_BASE_PATH}`);
  });

  it("the Worker asks the container for the mapped path", () => {
    // The proxy is where the base path lands: the request the container sees
    // carries the path `containerPathFor` produces.
    const index = read("apps/digichat-cloudflare/src/index.ts");
    expect(index).toMatch(/withContainerPath\(request, url\.pathname\)/);
    expect(index).toMatch(/target\.pathname = containerPathFor\(pathname\)/);
  });
});
