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
 * boot 503. Behavioral pins on the pure helper module (importable under
 * vitest, unlike index.ts) plus wiring pins that all three container
 * wrappers branch to the 410.
 */
const here = dirname(fileURLToPath(import.meta.url));

function stackSource(): string {
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
    const body = (await res.json()) as { code: string; message: string };
    expect(body.code).toBe(CONTAINER_EVSCITED_CODE);
    expect(body.code).toBe("container_evicted");
    expect(body.message).toContain("stack");
  });
});

describe("all three containers wire the evicted branch", () => {
  it("imports the eviction helpers", () => {
    expect(stackSource()).toContain('from "./container-errors"');
    expect(stackSource()).toContain("isContainerEvictedError");
    expect(stackSource()).toContain("containerEvictedResponse");
  });

  it("branches to the 410 in every container catch block", () => {
    const source = stackSource();
    for (const service of ["stack", "mcp", "digichat"]) {
      expect(source).toContain(`return containerEvictedResponse("${service}", message);`);
    }
  });

  it("keeps the boot 503 for the non-evicted path", () => {
    const source = stackSource();
    for (const service of ["stack", "mcp", "digichat"]) {
      expect(source).toContain(`return containerBootingResponse("${service}", message);`);
    }
  });
});
