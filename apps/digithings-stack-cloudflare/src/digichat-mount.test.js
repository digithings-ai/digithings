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
import { legacyEmbedEnabledValue } from "../../digichat-cloudflare/src/embed-flag";
import {
  getStackStatus,
  resetStackModuleHealth,
  runIsolated,
} from "./route-modules";

/**
 * Folded digichat mount (slice 3, #4689).
 *
 * Behavioral tests drive the folded digichat group the same way slices 1-2
 * do: the mount check proves the stack adapter reuses the standalone
 * worker's own predicate (same function, not a copy), and the fault-injection
 * checks prove a digichat failure degrades ONLY its own paths (503) while
 * every sibling group keeps serving.
 *
 * Auth stays in-container: there is deliberately no edge-gating test here —
 * the stack worker applies no 401/JWT check on digichat paths (pinned by the
 * absence of any auth check in the digichat branch, see the index.ts pins).
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

describe("digichat mount (same predicate as the standalone worker)", () => {
  it("re-exports the standalone worker's shouldProxyToDigiChat (not a copy)", () => {
    expect(shouldProxyToDigiChat).toBe(standalonePredicate);
  });

  it("matches every folded path from the standalone paths.test.ts contract", () => {
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
    ]) {
      expect(shouldProxyToDigiChat(path)).toBe(true);
    }
  });

  it("leaves Pages marketing/chat shells and other groups' paths alone", () => {
    for (const path of [
      "/",
      "/chat",
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
// paths.ts, and the fold re-exports that function. So the properties worth
// pinning changed shape:
//
//   - EQUALITY BY CONSTRUCTION — the folded id IS the standalone derivation
//     (same function object), not a second copy that can drift.
//   - DERIVATION — the id is a function of the rev, and rev-less is the legacy
//     fallback. This is the property the deleted literal used to fake: it
//     asserted one hard-coded point, not the function that produced it.
//
// A test asserting `sharedDigichatContainerId(rev) === "shared-" + rev` is what
// makes a hand-pinned id impossible to reintroduce: reintroducing one means the
// function ignores its argument, and these die.
describe("folded digichat container id is derived, not pinned (DIG-3814)", () => {
  const REVS = [
    "3528cf9f7ab1",
    "0000000000",
    "abcdef012345",
    "fedcba987654",
  ];

  it("the fold re-exports the standalone derivation itself, not a copy", () => {
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

  it("folded and standalone agree on every rev (the property the literal replaced)", () => {
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

  it("strips anything that is not a hex rev before it becomes a Container name", () => {
    // The derived string reaches getContainer as a Durable Object name, so a
    // malformed value must degrade to the fallback rather than pass through.
    expect(sharedDigichatContainerId("../../etc/passwd")).toBe(
      LEGACY_SHARED_DIGICHAT_CONTAINER_ID,
    );
    expect(sharedDigichatContainerId("  3528CF9F7AB1  ")).toBe("shared-3528cf9f7ab1");
  });

  it("never declares a Container id constant in the fold or the source module", () => {
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

  it("keeps the Next standalone port next to the predicate (one fold module)", () => {
    expect(source).toContain("DIGICHAT_PORT = 3000");
  });
});

describe("digichat index.ts wiring pins", () => {
  const source = readFileSync(join(here, "index.ts"), "utf-8");

  it("matches the branch on the standalone predicate (no copied path list)", () => {
    expect(source).toContain("shouldProxyToDigiChat(url.pathname)");
    const branch = source.slice(source.indexOf("shouldProxyToDigiChat(url.pathname)"));
    expect(branch).not.toContain('"/api/chat"');
    expect(branch).not.toContain('"/_dtchat');
  });

  it("proxies through the digichat container on :3000 with switchPort", () => {
    expect(source).toContain('"digichat"');
    expect(source).toContain('() => import("./digichat")');
    expect(source).toContain("getContainer(workerEnv.DIGICHAT, sharedDigichatContainerId(workerEnv.DIGICHAT_CONTAINER_REV))");
    expect(source).toContain("switchPort(request, DIGICHAT_PORT)");
  });

  it("applies no edge gating on digichat paths (auth stays in-container)", () => {
    const branchStart = source.indexOf("shouldProxyToDigiChat(url.pathname)");
    expect(branchStart).toBeGreaterThan(-1);
    const branchEnd = source.indexOf("Dedicated digiquant-mcp container", branchStart);
    expect(branchEnd).toBeGreaterThan(branchStart);
    const branch = source.slice(branchStart, branchEnd);
    expect(branch).not.toContain("401");
    expect(branch).not.toContain("unauthorized");
    expect(branch).not.toContain("x-digi-mcp-key");
    expect(branch).not.toContain("JWT");
  });

  it("keeps the /_dtchat asset prefix (no clash with Pages /_next)", () => {
    // The predicate owns the prefix; this pins the contract from this side so
    // a predicate swap that drops /_dtchat fails here, not in production.
    expect(shouldProxyToDigiChat("/_dtchat/_next/static/x.js")).toBe(true);
  });

  it("mounts the digichat branch before the container-routes catch-all", () => {
    const chatBranch = source.indexOf("shouldProxyToDigiChat(url.pathname)");
    const catchAll = source.indexOf('runIsolated("container-routes"');
    expect(chatBranch).toBeGreaterThan(-1);
    expect(catchAll).toBeGreaterThan(chatBranch);
  });

  it("pins the digichat image bind (:3000 on 0.0.0.0, same as standalone)", () => {
    const dockerfile = readFileSync(
      join(here, "..", "..", "..", "Dockerfile.digichat-cloudflare"),
      "utf-8",
    );
    expect(dockerfile).toContain("EXPOSE 3000");
    expect(dockerfile).toContain("ENV PORT=3000");
    expect(dockerfile).toContain("ENV HOSTNAME=0.0.0.0");
  });
});

describe("digichat embed-flag parity", () => {
  it("the inline envVars derivation matches legacyEmbedEnabledValue for every input", () => {
    // index.ts keeps the OR inline so the envVars key↔ref pin still pairs
    // DIGICHAT_EMBED_ENABLED with its own entry (see DigiChatContainer.envVars
    // in index.ts). This truth table pins the inline copy equal to the
    // canonical helper for all 9 input combinations.
    const source = readFileSync(join(here, "index.ts"), "utf-8");
    expect(source).toContain(
      'env.DIGICHAT_EMBED_ENABLED === "1" || env.DIGICHAT_LEGACY_EMBED_ENABLED === "1"',
    );
    const inline = (embed, legacy) =>
      embed === "1" || legacy === "1" ? "1" : "0";
    for (const embed of ["1", "0", undefined]) {
      for (const legacy of ["1", "0", undefined]) {
        expect(inline(embed, legacy)).toBe(legacyEmbedEnabledValue(legacy, embed));
      }
    }
  });
});
