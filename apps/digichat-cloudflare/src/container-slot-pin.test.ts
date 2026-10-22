import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../..");
const WRANGLER = join(repoRoot, "apps/digichat-cloudflare/wrangler.toml");
const INDEX = join(repoRoot, "apps/digichat-cloudflare/src/index.ts");
const CONTRACT = join(repoRoot, "config/contract/contract.yaml");

/**
 * The container slot, pinned (DIG-4487).
 *
 * `max_instances` is the number of RUNNING container instances the Worker may
 * hold. The digichat container id is derived from the deploying commit, so
 * every deploy addresses a NEW id while the previous id's instance is still
 * running — warm, or draining for up to 15 minutes after the rollout's
 * SIGTERM. With one slot the new instance cannot start until the old one has
 * fully exited, and every request that needs a container start fails with
 * "Maximum number of running container instances exceeded" (27 error rows and
 * 34 failed client requests on 2026-10-19).
 *
 * Two slots give the rollout a free slot. The second one is only used while a
 * previous id's instance drains: in steady state the Worker addresses one id
 * and runs one instance.
 */
describe("the digichat container slot", () => {
  it("wrangler.toml allows two instances, so a rollout cannot starve a cold start", () => {
    expect(readFileSync(WRANGLER, "utf8")).toMatch(/^max_instances = 2$/m);
  });

  it("keeps the reason next to the number", () => {
    const lines = readFileSync(WRANGLER, "utf8").split("\n");
    const at = lines.findIndex((line) => line === "max_instances = 2");
    expect(at).toBeGreaterThan(-1);
    const why = lines.slice(Math.max(0, at - 12), at).join("\n");
    // The why travels with the number: a future edit that drops the comment
    // loses the reason the slot is two.
    expect(why).toContain("DIG-4487");
    expect(why).toContain("drain");
    expect(why).toContain("deploy");
  });

  it("the hand-maintained contract agrees with the shipped wrangler.toml", () => {
    const contract = readFileSync(CONTRACT, "utf8");
    const block = contract
      .split(/\n(?=- worker: )/)
      .find(
        (chunk) =>
          chunk.includes("worker: digithings-digichat") &&
          chunk.includes("type: container") &&
          chunk.includes("DigiChatContainer"),
      );
    expect(block, "the digichat container binding row in contract.yaml").toBeTruthy();
    expect(block).toMatch(/max_instances: 2/);
  });
});

describe("the proxy call site", () => {
  const indexSource = readFileSync(INDEX, "utf-8");

  it("routes the container call through the bounded retry", () => {
    expect(indexSource).toMatch(/import \{ fetchContainerWithRetry \} from "\.\/container-retry";/);
    // Wrapped only so a failed page/frame load renders as HTML (frame-safe-error.ts).
    // The request that reaches the container is the base-path-mapped one
    // (DIG-5121), so the wiring is pinned by NAME: computing a mapped request
    // and then fetching the original one would leave the container answering
    // at "/", which is a dead /chat route.
    expect(indexSource).toMatch(
      /return frameSafeErrorResponse\(\s*containerRequest,\s*await fetchContainerWithRetry\(containerRequest, \(req\) => container\.fetch\(req\)\),\s*\);/,
    );
  });

  it("keeps the container id derived from the deploying commit", () => {
    // The retry is about a busy slot, not about a different instance: the id
    // must still come from the deploy rev.
    expect(indexSource).toMatch(
      /const containerId = sharedDigichatContainerId\(workerEnv\.DIGICHAT_CONTAINER_REV\)/,
    );
  });

  it("does not retry the admin reset lever or the meta route", () => {
    // Both are served by the Worker itself and never reach the container.
    const retryAt = indexSource.indexOf("fetchContainerWithRetry(");
    const resetAt = indexSource.indexOf("digichatContainerReset(");
    const metaAt = indexSource.indexOf('"/_digichat/meta"');
    expect(retryAt).toBeGreaterThan(-1);
    expect(resetAt).toBeGreaterThan(-1);
    expect(metaAt).toBeGreaterThan(-1);
    expect(resetAt).toBeLessThan(retryAt);
    expect(metaAt).toBeLessThan(retryAt);
  });
});
