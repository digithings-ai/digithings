import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Pins the machine-readable boot 503s of all three containers (#4753).
 *
 * The digichat BFF keys its extended cold-boot retry budget off the
 * `container_booting` code plus the `Retry-After` header: only a 503 carrying
 * both gets the ~250s budget, every other 503 keeps the 15s budget. A
 * plain-text body (the pre-#4753 shape) or a missing header silently drops the
 * BFF back to the short budget, so the first send of a cold boot fails with
 * the unavailable-message again.
 *
 * Deliberately plain `.js`, same reason as wake-readiness.test.js: tsconfig
 * scopes `types` to @cloudflare/workers-types only, and index.ts imports
 * `cloudflare:workers` / `@cloudflare/containers`, so it cannot be imported
 * under plain vitest.
 */
const here = dirname(fileURLToPath(import.meta.url));

function stackSource() {
  return readFileSync(join(here, "index.ts"), "utf-8");
}

function helperSource() {
  const source = stackSource();
  const start = source.indexOf("export function containerBootingResponse(");
  expect(start).toBeGreaterThan(-1);
  const end = source.indexOf("export interface Env", start);
  expect(end).toBeGreaterThan(start);
  return source.slice(start, end);
}

describe("container boot 503s carry the boot code + Retry-After", () => {
  it("defines the boot code the BFF keys off", () => {
    expect(stackSource()).toContain(
      'export const CONTAINER_BOOTING_CODE = "container_booting"',
    );
  });

  it("answers JSON with a 503 status and a Retry-After header", () => {
    const helper = helperSource();
    expect(helper).toContain("Response.json(");
    expect(helper).toContain("code: CONTAINER_BOOTING_CODE");
    expect(helper).toContain("status: 503");
    expect(helper).toContain('"Retry-After"');
  });

  it("serves the boot 503 from all three containers", () => {
    const source = stackSource();
    for (const service of ["stack", "mcp", "digichat"]) {
      expect(source).toContain(`return containerBootingResponse("${service}", message);`);
    }
  });

  it("has no remaining plain-text container-not-ready 503", () => {
    expect(stackSource()).not.toContain("container not ready: ${message}`, {");
  });
});
