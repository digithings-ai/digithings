import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  CONTAINER_EVSCITED_CODE,
  containerEvictedResponse,
  isContainerEvictedError,
} from "./container-errors";

/**
 * DIG-3226: confirmed container evictions must not collapse into the generic
 * boot 503. Behavioral pins on the pure helper module (dependency-free, so
 * importable here) plus wiring pins that both remaining container wrappers
 * branch to the 410. (The digichat Container left this Worker on 2026-10-19;
 * apps/digichat-cloudflare carries its own copy of this wiring.)
 *
 * Deliberately plain `.js`, same reason as container-booting-503.test.js:
 * tsconfig scopes `types` to @cloudflare/workers-types only, so a `.ts`
 * test importing node: builtins fails typecheck.
 */
const here = dirname(fileURLToPath(import.meta.url));

function stackSource() {
  return readFileSync(join(here, "index.ts"), "utf-8");
}

describe("isContainerEvictedError", () => {
  it("matches the brief's named eviction signals", () => {
    expect(isContainerEvictedError("container instance is no longer active")).toBe(true);
    expect(isContainerEvictedError("Error: container-network-lost")).toBe(true);
  });

  it("matches eviction vocabulary case-insensitively", () => {
    expect(isContainerEvictedError("instance EVICTED by the platform")).toBe(true);
    expect(isContainerEvictedError(new Error("Durable Object eviction"))).toBe(true);
    expect(isContainerEvictedError("container network lost during fetch")).toBe(true);
  });

  it("does not match ordinary cold-start / timeout messages", () => {
    expect(isContainerEvictedError("port 8000 not ready after 180000ms")).toBe(false);
    expect(isContainerEvictedError("instanceGetTimeout: timed out waiting for ports")).toBe(false);
    expect(isContainerEvictedError("")).toBe(false);
  });
});

describe("containerEvictedResponse", () => {
  it("answers 410 with the evicted code and no Retry-After", async () => {
    const res = containerEvictedResponse("stack", "instance is no longer active");
    expect(res.status).toBe(410);
    expect(res.headers.get("Retry-After")).toBeNull();
    const body = await res.json();
    expect(body.code).toBe(CONTAINER_EVSCITED_CODE);
    expect(body.code).toBe("container_evicted");
    expect(body.message).toContain("stack");
  });
});

describe("the remaining container wires the evicted branch", () => {
  it("imports the eviction helpers", () => {
    expect(stackSource()).toContain('from "./container-errors"');
    expect(stackSource()).toContain("isContainerEvictedError");
    expect(stackSource()).toContain("containerEvictedResponse");
  });

  it("branches to the 410 in every container catch block", () => {
    // Each container has TWO guarded sites (startAndWaitForPorts catch +
    // containerFetch catch); exactly 2 each proves neither collapsed back
    // to the uniform 503 (a presence-only check cannot tell). The boot catch
    // reads the message out of the thrown value, the hop catch reads it out
    // of the classification (DIG-4928).
    const source = stackSource();
    const boot = 'return containerEvictedResponse("stack", message);';
    const hop = 'return containerEvictedResponse("stack", failure.message);';
    expect(source.split(boot).length - 1).toBe(1);
    expect(source.split(hop).length - 1).toBe(1);
    // The deleted digiquant-mcp container (DIG-5558) must not wire this again.
    expect(source).not.toContain('containerEvictedResponse("mcp"');
  });

  it("keeps the boot 503 for the non-evicted path", () => {
    const source = stackSource();
    expect(source).toContain('return containerBootingResponse("stack", message);');
    expect(source).not.toContain('containerBootingResponse("mcp"');
  });
});
