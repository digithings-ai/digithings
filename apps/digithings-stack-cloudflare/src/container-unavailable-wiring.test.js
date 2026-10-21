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
  it("guards both container classes' containerFetch catch", () => {
    // One guard per container class (DigiStackContainer, DigiQuantMcpContainer).
    const source = stackSource();
    expect(source.split("isNonErrorRejection(err)").length - 1).toBe(2);
  });

  it("answers the unavailable 503 in both container classes", () => {
    const source = stackSource();
    for (const service of ["stack", "mcp"]) {
      const needle = `return containerUnavailableResponse("${service}", description);`;
      expect(source.split(needle).length - 1).toBe(1);
    }
  });

  it("guards the hop, not the cold start", () => {
    // The guard belongs to the containerFetch catch: a hop that rejected with
    // an opaque value is a failed request. The start path already answers a
    // retryable 503 (container_booting), so it never escapes and must keep
    // that answer.
    const source = stackSource();
    for (const service of ["stack", "mcp"]) {
      const guard = source.indexOf(
        `return containerUnavailableResponse("${service}", description);`,
      );
      const hop = source.indexOf("this.containerFetch(");
      expect(guard).toBeGreaterThan(hop);
    }
  });

  it("keeps the real Error path unchanged", () => {
    // A real error keeps its own classification: the eviction 410, the failed
    // 503, and the rethrow of anything else.
    const source = stackSource();
    for (const service of ["stack", "mcp"]) {
      expect(source).toContain(`return containerEvictedResponse("${service}", message);`);
      expect(source).toContain(`return containerFailedResponse("${service}", message);`);
    }
    expect(source.split("throw err;").length - 1).toBe(2);
  });
});

describe("the Worker-side retry helper answers a rejection that is not an Error", () => {
  it("guards the catch of the retry loop", () => {
    const source = retrySource();
    expect(source).toContain("isNonErrorRejection(error)");
    expect(source).toContain("containerUnavailableResponse(");
  });

  it("does not replay the request after an opaque rejection", () => {
    // The guard returns before the catch's retry counter moves: a value that
    // came out of the hop says nothing about whether the request reached the
    // container, so a second attempt could submit it twice.
    const source = retrySource();
    const catchStart = source.indexOf("} catch (error) {");
    const guard = source.indexOf("if (isNonErrorRejection(error)) {", catchStart);
    const retry = source.indexOf("attemptIndex += 1;", guard);
    expect(catchStart).toBeGreaterThan(-1);
    expect(guard).toBeGreaterThan(catchStart);
    expect(retry).toBeGreaterThan(guard);
  });
});
