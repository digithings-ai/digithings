import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DIGICHAT_PORT,
  digichatContainerRev,
  sharedDigichatContainerId,
  shouldProxyToDigiChat,
} from "./digichat";
import { shouldProxyToDigiChat as standalonePredicate } from "../../digichat-cloudflare/src/paths";
import {
  digichatContainerRev as standaloneRev,
  sharedDigichatContainerId as standaloneContainerId,
  LEGACY_SHARED_DIGICHAT_CONTAINER_ID,
} from "../../digichat-cloudflare/src/paths";
import {
  getStackStatus,
  resetStackModuleHealth,
  runIsolated,
} from "./route-modules";

/**
 * digichat adapter pins (slice 3, #4689; the stack fold was dropped 2026-10-19).
 *
 * The stack Worker no longer mounts a digichat route group — the client surface
 * lives on `digithings-digichat` (`apps/digichat-cloudflare`). What remains here
 * is the adapter shim `digichat.ts`, which re-exports the standalone worker's own
 * predicate/derivation (same functions, not copies), so the mount pins below
 * prove the re-export and the separation pins prove index.ts does not mount it.
 *
 * The `runIsolated` checks exercise the isolation primitive itself with the
 * "digichat" group label; they do not assert that the group is still wired.
 *
 * Deliberately plain `.js`, same reason as stack-isolation.test.js:
 * tsconfig scopes `types` to @cloudflare/workers-types only.
 */

const here = dirname(fileURLToPath(import.meta.url));

afterEach(() => {
  resetStackModuleHealth();
  vi.restoreAllMocks();
});

function ok(text = "ok") {
  return new Response(text, { status: 200 });
}

describe("digichat adapter (same predicate as the standalone worker)", () => {
  it("re-exports the standalone worker's shouldProxyToDigiChat (not a copy)", () => {
    expect(shouldProxyToDigiChat).toBe(standalonePredicate);
  });

  it("matches every digichat path from the standalone paths.test.ts contract", () => {
    for (const path of [
      "/embed",
      "/embed/",
      "/api/chat",
      "/api/chat/stream",
      "/api/embed/tenant-config",
      "/api/byok/test",
      "/api/plan-proof",
      "/api/plan-proof/mint",
      "/api/health",
      "/_dtchat/_next/static/x.js",
      // DIG-5121: the /chat cutover moved the public chat path off the Pages
      // marketing shell onto the standalone worker (`digithings.ai/chat*`).
      // The predicate is shared by construction, so /chat now matches here
      // too — the stack itself still mounts no digichat route (see the
      // separation pins below), it only borrows the same path table.
      "/chat",
    ]) {
      expect(shouldProxyToDigiChat(path)).toBe(true);
    }
  });

  it("leaves Pages marketing/chat shells and other groups' paths alone", () => {
    for (const path of [
      "/",
      // The OCC invite shell stays a Pages shell behind the worker's gate,
      // so it is not a digichat container path (DIG-5121).
      "/chat/occ",
      "/docs",
      "/_next/static/x.js",
      "/dashboard-api/portfolio",
      "/_stack/mcp/zammad/mcp",
      "/v1/market/tickers",
      "/_stack/key/healthz",
    ]) {
      expect(shouldProxyToDigiChat(path)).toBe(false);
    }
  });

  it("pins the Next standalone port", () => {
    expect(DIGICHAT_PORT).toBe(3000);
  });
});

// DIG-3814: the Container id used to be a hand-edited literal this file pinned
// twice — once for equality with the standalone worker, once for the value
// "shared-v10". Both pins were the same manual step: the two literals had to
// be bumped in step, by hand, and a stale instance was already the mitigation
// for a warm container serving an old DIGICHAT_EMBED_TENANTS (DIG-1381 Act B1).
//
// The id is now derived from the deploying commit by the standalone worker's own
// paths.ts, and this adapter re-exports that function. So the properties worth
// pinning changed shape:
//
//   - EQUALITY BY CONSTRUCTION — the adapter's id IS the standalone derivation
//     (same function object), not a second copy that can drift.
//   - DERIVATION — the id is a function of the rev, and rev-less is the legacy
//     fallback. This is the property the deleted literal used to fake: it
//     asserted one hard-coded point, not the function that produced it.
//
// A test asserting `sharedDigichatContainerId(rev) === "shared-" + rev` is what
// makes a hand-pinned id impossible to reintroduce: reintroducing one means the
// function ignores its argument, and these die.
describe("digichat container id is derived, not pinned (DIG-3814)", () => {
  const REVS = [
    "3528cf9f7ab1",
    "0000000000",
    "abcdef012345",
    "fedcba987654",
  ];

  it("the adapter re-exports the standalone derivation itself, not a copy", () => {
    // Object identity: the strongest available statement of "by construction".
    // A fold that reimplemented the function would fail here even when both
    // happened to return equal values today.
    expect(sharedDigichatContainerId).toBe(standaloneContainerId);
    expect(digichatContainerRev).toBe(standaloneRev);
  });

  it("derives the id from the deploying commit's rev", () => {
    for (const rev of REVS) {
      expect(sharedDigichatContainerId(rev)).toBe(`shared-${rev}`);
    }
  });

  it("adapter and standalone agree on every rev (the property the literal replaced)", () => {
    for (const rev of REVS) {
      expect(sharedDigichatContainerId(rev)).toBe(standaloneContainerId(rev));
      expect(digichatContainerRev(rev)).toBe(standaloneRev(rev));
    }
  });

  it("falls back to the legacy id when a deploy carried no rev", () => {
    // Unset is an honest state — a bare `npx wrangler deploy` — not an error.
    for (const empty of [undefined, null, "", "   "]) {
      expect(sharedDigichatContainerId(empty)).toBe(
        LEGACY_SHARED_DIGICHAT_CONTAINER_ID,
      );
      expect(digichatContainerRev(empty)).toBeNull();
    }
  });

  it("rejects anything that is not a hex rev instead of minting a new instance", () => {
    // The derived string reaches getContainer as a Durable Object name, so a
    // malformed value must degrade to the fallback rather than pass through.
    expect(sharedDigichatContainerId("../../etc/passwd")).toBe(
      LEGACY_SHARED_DIGICHAT_CONTAINER_ID,
    );
    expect(sharedDigichatContainerId("  3528CF9F7AB1  ")).toBe("shared-3528cf9f7ab1");
  });

  it("never declares a Container id constant in the adapter or the source module", () => {
    // The literal is gone, not renamed: `export const SHARED_…_CONTAINER_ID` is
    // what a future hand-pick would look like, and it must not come back.
    const foldSource = readFileSync(join(here, "digichat.ts"), "utf-8");
    const pathsSource = readFileSync(
      join(here, "..", "..", "digichat-cloudflare", "src", "paths.ts"),
      "utf-8",
    );
    expect(foldSource).not.toMatch(/SHARED_DIGICHAT_CONTAINER_ID(?!_LEGACY)/);
    expect(foldSource).not.toMatch(/export\s+const\s+SHARED_/);
    expect(pathsSource).not.toMatch(/export\s+const\s+SHARED_DIGICHAT_CONTAINER_ID/);
    // Control: the matcher fires on the legacy constant's own line.
    expect(pathsSource).toMatch(/export const LEGACY_SHARED_DIGICHAT_CONTAINER_ID/);
  });
});

describe("digichat isolation (own-paths-503 + sibling-health)", () => {
  it("a digichat failure degrades ONLY its own paths with a 503", async () => {
    const chatRes = await runIsolated("digichat", async () => {
      throw new Error("digichat bundle exploded");
    }, async () => ok());
    expect(chatRes.status).toBe(503);
    expect(await chatRes.text()).toContain("digichat unavailable");

    // Siblings keep serving: every other group is unaffected by the
    // digichat outage.
    for (const sibling of ["key-proxy", "mcp-edge", "market-data", "dashboard-api"]) {
      const res = await runIsolated(sibling, async () => ({}), async () => ok());
      expect(res.status).toBe(200);
    }

    const status = getStackStatus();
    expect(status.modules["digichat"]).toEqual({
      state: "degraded",
      lastError: "digichat bundle exploded",
    });
    expect(status.modules["key-proxy"]).toEqual({ state: "loaded", lastError: null });
    expect(status.modules["mcp-edge"]).toEqual({ state: "loaded", lastError: null });
    expect(status.modules["market-data"]).toEqual({ state: "loaded", lastError: null });
    expect(status.modules["dashboard-api"]).toEqual({ state: "loaded", lastError: null });
    expect(status.modules["container-routes"]).toEqual({
      state: "unloaded",
      lastError: null,
    });
  });

  it("a throwing digichat route handler degrades its own group", async () => {
    const res = await runIsolated("digichat", async () => ({}), async () => {
      throw new Error("next standalone blew up");
    });
    expect(res.status).toBe(503);
    expect(await res.text()).toContain("digichat unavailable");
    expect(getStackStatus().modules["digichat"]).toEqual({
      state: "degraded",
      lastError: "next standalone blew up",
    });
  });

  it("heal-back clears the digichat entry on later success", async () => {
    await runIsolated("digichat", async () => {
      throw new Error("transient");
    }, async () => ok());
    expect(getStackStatus().modules["digichat"].state).toBe("degraded");

    const res = await runIsolated("digichat", async () => ({}), async () => ok());
    expect(res.status).toBe(200);
    expect(getStackStatus().modules["digichat"]).toEqual({
      state: "loaded",
      lastError: null,
    });
  });
});

describe("digichat adapter source pins", () => {
  const source = readFileSync(join(here, "digichat.ts"), "utf-8");

  it("reuses the standalone worker's paths module instead of reimplementing routes", () => {
    expect(source).toContain('from "../../digichat-cloudflare/src/paths"');
    expect(source).toContain("shouldProxyToDigiChat");
    expect(source).toContain("sharedDigichatContainerId");
    expect(source).not.toContain('"/api/chat"');
    expect(source).not.toContain('"/api/embed/"');
    expect(source).not.toContain('"/api/byok/"');
    expect(source).not.toContain('"/api/plan-proof"');
    expect(source).not.toContain('"/_dtchat/"');
  });

  it("keeps the Next standalone port next to the predicate (one adapter module)", () => {
    expect(source).toContain("DIGICHAT_PORT = 3000");
  });
});

describe("digichat separation pins (Chris, 2026-10-19)", () => {
  const source = readFileSync(join(here, "index.ts"), "utf-8");

  it("does NOT mount a digichat branch — the surface stays on digithings-digichat", () => {
    expect(source).not.toContain("shouldProxyToDigiChat(url.pathname)");
    expect(source).not.toContain('() => import("./digichat")');
    expect(source).not.toContain("getContainer(workerEnv.DIGICHAT");
    expect(source).not.toContain("switchPort(request, DIGICHAT_PORT)");
    // The orphaned class went with the fold (2026-10-19). Pinning its absence
    // keeps a re-added container from shipping without a binding or a route —
    // the exact dead-code shape this removal cleaned up.
    expect(source).not.toContain("class DigiChatContainer");
    expect(source).not.toContain("DurableObjectNamespace<DigiChatContainer>");
  });

  it("does NOT gate the OCC shell here — the invite gate stays on the digichat worker", () => {
    expect(source).not.toContain("legacyInviteGate(");
    expect(source).not.toContain("isLegacyInviteShellPath(");
  });

  it("keeps the /_dtchat asset prefix (no clash with Pages /_next)", () => {
    // The predicate owns the prefix; this pins the contract from this side so
    // a predicate swap that drops /_dtchat fails here, not in production.
    expect(shouldProxyToDigiChat("/_dtchat/_next/static/x.js")).toBe(true);
  });

  it("pins the digichat image bind (:3000 on 0.0.0.0, same as standalone)", () => {
    const dockerfile = readFileSync(
      join(here, "..", "..", "..", "infra/docker/Dockerfile.digichat-cloudflare"),
      "utf-8",
    );
    expect(dockerfile).toContain("EXPOSE 3000");
    expect(dockerfile).toContain("ENV PORT=3000");
    expect(dockerfile).toContain("ENV HOSTNAME=0.0.0.0");
  });
});

