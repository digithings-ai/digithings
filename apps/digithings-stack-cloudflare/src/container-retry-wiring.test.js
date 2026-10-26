import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * DIG-4477: every container-backed route in the stack Worker goes through the
 * retry-once wrapper, and the container wrapper classifies a failed container
 * separately from a booting one.
 *
 * Behavioural pins on the pure helper live in container-retry.test.ts; index.ts
 * cannot be imported here (it imports `cloudflare:workers` /
 * `@cloudflare/containers`), so the WIRING is pinned by source text — the same
 * split container-evicted-410.test.js uses for the 410 contract.
 *
 * Deliberately plain `.js`: tsconfig scopes `types` to
 * @cloudflare/workers-types only, so a `.ts` test importing node: builtins
 * fails typecheck.
 */
const here = dirname(fileURLToPath(import.meta.url));

function stackSource() {
  return readFileSync(join(here, "index.ts"), "utf-8");
}

describe("the stack Worker imports the retry helper", () => {
  it("imports it from ./container-retry", () => {
    expect(stackSource()).toContain('from "./container-retry"');
    expect(stackSource()).toContain("fetchWithContainerRetry");
  });
});

describe("every container-backed route retries once", () => {
  it("wraps every container.fetch call site", () => {
    const source = stackSource();
    // Three container-backed routes: the digikey proxy, the in-container MCP
    // edge proxy and the hostname proxy (graph./key./search.). The reserved
    // digiquant-mcp hostname is Worker-native since DIG-2913 (a Durable
    // Object, no container.fetch), so it is deliberately not counted.
    const fetches = source.match(/container\.fetch\(/g) ?? [];
    const wrapped = source.match(/fetchWithContainerRetry\(/g) ?? [];
    expect(fetches).toHaveLength(3);
    // One wrapper per fetch: a new unwrapped call site would make the counts
    // diverge, and a wrapper without a fetch would make them diverge too.
    expect(wrapped).toHaveLength(fetches.length);
  });

  it("replays the request from a fresh clone on every attempt", () => {
    // The body of a consumed Request cannot be replayed, so each attempt
    // needs its own clone. One per container-backed route.
    const source = stackSource();
    expect(source.match(/request\.clone\(\)/g) ?? []).toHaveLength(3);
    // A clone hoisted ABOVE the retry closure would keep the count at 3 and
    // this test green, while attempt 2 then tries to re-send a consumed body
    // (TypeError) and the replay silently stops working. Every clone must be
    // an inline argument of the attempt.
    expect(source).not.toMatch(/=\s*request\.clone\(\)/);
  });

  it("wraps every container fetch in a closure", () => {
    const source = stackSource();
    expect(source.match(/fetchWithContainerRetry\(\(\) =>/g) ?? []).toHaveLength(3);
  });

  it("converts the containers package's 500 into the failed-container answer", () => {
    // @cloudflare/containers 0.3.7 answers a container that died mid-request
    // with a 500 instead of throwing, so the recycle has to be recognised on
    // the RESPONSE — once per container class.
    const source = stackSource();
    expect(source).toContain("containerRestartMessage");
    expect(source.split("await containerRestartMessage(response)").length - 1).toBe(2);
  });

  it("keeps the MCP edge proxy forwarding to the mapped port", () => {
    // Pinned so the retry wrapper cannot quietly change what the MCP edge
    // path forwards (zammad-mcp-route.test.js pins the same call shape).
    expect(stackSource()).toContain("switchPort(forwarded, port)");
  });
});

describe("the container wrapper separates a failed container from a booting one", () => {
  it("imports the failed-container classifier", () => {
    expect(stackSource()).toContain("isContainerFailedError");
    expect(stackSource()).toContain("containerFailedResponse");
  });

  it("branches to the failed-container answer in every container catch block", () => {
    // Each container has TWO guarded sites (startAndWaitForPorts catch +
    // containerFetch catch); exactly 2 each proves neither collapsed back to
    // the uniform boot 503 (a presence-only check cannot tell). The boot catch
    // reads the message out of the thrown value, the hop catch reads it out
    // of the classification (DIG-4928).
    const source = stackSource();
    for (const service of ["stack", "mcp"]) {
      const boot = `return containerFailedResponse("${service}", message);`;
      const hop = `return containerFailedResponse("${service}", failure.message);`;
      expect(source.split(boot).length - 1).toBe(1);
      expect(source.split(hop).length - 1).toBe(1);
    }
  });

  it("keeps the boot 503 for a container that is still starting", () => {
    const source = stackSource();
    for (const service of ["stack", "mcp"]) {
      expect(source).toContain(`return containerBootingResponse("${service}", message);`);
    }
  });

  it("keeps the evicted 410 for a confirmed eviction", () => {
    const source = stackSource();
    for (const service of ["stack", "mcp"]) {
      const boot = `return containerEvictedResponse("${service}", message);`;
      const hop = `return containerEvictedResponse("${service}", failure.message);`;
      expect(source.split(boot).length - 1).toBe(1);
      expect(source.split(hop).length - 1).toBe(1);
    }
  });
});
