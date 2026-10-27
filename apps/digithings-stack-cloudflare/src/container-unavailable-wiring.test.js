import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * DIG-4928: the wiring of the "the container hop rejected with a value that
 * is not an Error" guard.
 *
 * The behaviour is pinned in container-unavailable.test.ts; index.ts cannot be
 * imported here (it imports `cloudflare:workers` / `@cloudflare/containers`),
 * so the WIRING is pinned by source text — the same split
 * container-retry-wiring.test.js uses for the retry contract.
 *
 * Deliberately plain `.js`: tsconfig scopes `types` to
 * @cloudflare/workers-types only, so a `.ts` test importing node: builtins
 * fails typecheck.
 */
const here = dirname(fileURLToPath(import.meta.url));

function stackSource() {
  return readFileSync(join(here, "index.ts"), "utf-8");
}

function retrySource() {
  return readFileSync(join(here, "container-retry.ts"), "utf-8");
}

describe("every container hop answers a rejection that is not an Error", () => {
  it("classifies the failure in one place in the one remaining container class", () => {
    // The classification lives in the catch of each container class. Only
    // DigiStackContainer is left: the digiquant-mcp container and its class
    // were deleted in DIG-5558 (the Worker-native DigiQuantMcpAgent has no
    // container hop), so this count is the absence pin — a second class would
    // bring back a second call site here.
    const source = stackSource();
    expect(source).not.toContain("DigiQuantMcpContainer");
    expect(source.split("classifyContainerHopFailure(err)").length - 1).toBe(1);
  });

  it("answers the unavailable 503 in the one remaining container class", () => {
    const source = stackSource();
    expect(source.split('return containerUnavailableResponse("stack");').length - 1).toBe(1);
    // The retired MCP container's service tag must not linger in this Worker.
    expect(source).not.toContain('containerUnavailableResponse("mcp")');
  });

  it("keeps the cause of the failure out of the answer", () => {
    // The answer carries the service and the fixed detail, never the
    // description of the rejected value: internal detail does not leave the
    // Worker (the shared package holds the same contract).
    const source = stackSource();
    expect(source).not.toContain('containerUnavailableResponse("stack",');
    expect(source).not.toContain('containerUnavailableResponse("mcp",');
  });

  it("guards the hop, not the cold start", () => {
    // The guard belongs to the containerFetch catch: a hop that rejected with
    // an opaque value is a failed request. The start path already answers a
    // retryable 503 (container_booting), so it never escapes and must keep
    // that answer.
    const source = stackSource();
    const guard = source.indexOf('return containerUnavailableResponse("stack");');
    const hop = source.indexOf("this.containerFetch(");
    expect(guard).toBeGreaterThan(hop);
  });

  it("keeps the real Error path unchanged", () => {
    // A real error keeps its own classification: the eviction 410, the failed
    // 503, and the rethrow of anything else.
    const source = stackSource();
    expect(source).toContain('return containerEvictedResponse("stack", failure.message);');
    expect(source).toContain('return containerFailedResponse("stack", failure.message);');
    expect(source.split("throw err;").length - 1).toBe(1);
  });
});

describe("the Worker-side retry helper answers a rejection that is not an Error", () => {
  it("guards the catch of the retry loop", () => {
    const source = retrySource();
    expect(source).toContain("classifyContainerHopFailure(error)");
    expect(source).toContain("containerUnavailableResponse(");
  });

  it("does not replay the request after an opaque rejection", () => {
    // The guard returns before the catch's retry counter moves: a value that
    // came out of the hop says nothing about whether the request reached the
    // container, so a second attempt could submit it twice.
    const source = retrySource();
    const catchStart = source.indexOf("} catch (error) {");
    const guard = source.indexOf('if (failure.kind === "unavailable") {', catchStart);
    const retry = source.indexOf("attemptIndex += 1;", guard);
    expect(catchStart).toBeGreaterThan(-1);
    expect(guard).toBeGreaterThan(catchStart);
    expect(retry).toBeGreaterThan(guard);
  });

  it("keeps the cause of the failure out of the answer", () => {
    const source = retrySource();
    expect(source).not.toContain("containerUnavailableResponse(options.service ?? \"stack\",");
  });
});
