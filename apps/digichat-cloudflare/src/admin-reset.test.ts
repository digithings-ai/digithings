import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { DIGICHAT_ADMIN_KEY_HEADER, digichatContainerReset } from "./admin-reset";
import { SHARED_DIGICHAT_CONTAINER_ID } from "./paths";

const KEY = "fixture-admin-key";
const URL_ = "https://digithings.ai/_digichat-admin/container/reset";

/** A fresh destroy stub; assertion helpers also check it stayed argument-free. */
function destroyStub() {
  return vi.fn(async () => {});
}

/** Extracts the `envVars = { ... };` block from index.ts (throws if renamed). */
function envVarsBlock(source: string): string {
  const match = source.match(/envVars = \{([\s\S]*?)\n {2}\};/);
  if (!match) throw new Error("could not locate the `envVars = { ... };` block in index.ts");
  return match[1];
}

describe("digichatContainerReset", () => {
  it("answers 405 with an Allow: POST header on any non-POST method", async () => {
    for (const method of ["GET", "PUT", "DELETE", "PATCH", "HEAD"]) {
      const destroy = destroyStub();
      const res = await digichatContainerReset(
        new Request(URL_, { method, headers: { [DIGICHAT_ADMIN_KEY_HEADER]: KEY } }),
        KEY,
        destroy,
      );
      expect(res.status, `${method} should be 405`).toBe(405);
      expect(res.headers.get("Allow")).toBe("POST");
      expect(destroy).not.toHaveBeenCalled();
    }
  });

  it("fails closed with 404 when DIGICHAT_ADMIN_KEY is unset", async () => {
    const destroy = destroyStub();
    const res = await digichatContainerReset(
      new Request(URL_, { method: "POST", headers: { [DIGICHAT_ADMIN_KEY_HEADER]: KEY } }),
      undefined,
      destroy,
    );
    expect(res.status).toBe(404);
    expect(destroy).not.toHaveBeenCalled();
  });

  it("fails closed with 404 when the header is missing or wrong", async () => {
    const cases: Record<string, string>[] = [{}, { [DIGICHAT_ADMIN_KEY_HEADER]: "wrong" }];
    for (const headers of cases) {
      const destroy = destroyStub();
      const res = await digichatContainerReset(
        new Request(URL_, { method: "POST", headers }),
        KEY,
        destroy,
      );
      expect(res.status).toBe(404);
      expect(destroy).not.toHaveBeenCalled();
    }
  });

  it("destroys the instance exactly once and returns the documented 200 JSON", async () => {
    const destroy = destroyStub();
    const res = await digichatContainerReset(
      new Request(URL_, { method: "POST", headers: { [DIGICHAT_ADMIN_KEY_HEADER]: KEY } }),
      KEY,
      destroy,
    );
    expect(res.status).toBe(200);
    expect(destroy).toHaveBeenCalledTimes(1);
    // Control that must fail for a broken matcher: the lever takes no arguments.
    expect(destroy.mock.calls[0]).toEqual([]);
    const body = await res.json();
    expect(body).toEqual({
      ok: true,
      action: "container_destroyed",
      instance: SHARED_DIGICHAT_CONTAINER_ID,
    });
  });

  it("never echoes the configured key in a 404 body", async () => {
    const destroy = destroyStub();
    const res = await digichatContainerReset(
      new Request(URL_, { method: "POST", headers: { [DIGICHAT_ADMIN_KEY_HEADER]: "wrong" } }),
      KEY,
      destroy,
    );
    expect(res.status).toBe(404);
    const text = await res.text();
    expect(text).not.toContain(KEY);
    expect(text).not.toContain("shared-v15");
  });
});

describe("DIGICHAT_ADMIN_KEY stays Worker-only", () => {
  const indexSource = readFileSync(join(__dirname, "index.ts"), "utf-8");

  it("is declared on Env with a worker-only comment", () => {
    expect(indexSource).toMatch(/DIGICHAT_ADMIN_KEY\?:\s*string;/);
    expect(indexSource).toMatch(/never forwarded to the\s*\n?\s*\*?\s*container/);
  });

  it("is NOT forwarded into the container envVars block", () => {
    expect(envVarsBlock(indexSource)).not.toContain("DIGICHAT_ADMIN_KEY");
  });

  it("wires the reset path to the reset handler before the container proxy", () => {
    const resetAt = indexSource.indexOf('"/_digichat-admin/container/reset"');
    const zammadAt = indexSource.indexOf("const isZammadMcp =");
    expect(resetAt).toBeGreaterThan(-1);
    expect(resetAt).toBeLessThan(zammadAt);
    expect(indexSource).toMatch(/DIGICHAT_ADMIN_RESET_PATH\)\s*\{\s*return digichatContainerReset\(/);
  });
});
