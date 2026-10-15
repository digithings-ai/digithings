import { beforeEach, describe, expect, it, vi } from "vitest";

const VALID_TEXT = `version: 1
deployment:
  slug: devkit-fixture
  backend:
    type: digigraph
`;

describe("POST /api/devkit/validate", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  async function post(url: string, body: unknown) {
    const { POST } = await import("./route");
    return POST(
      new Request(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: typeof body === "string" ? body : JSON.stringify(body),
      }),
    );
  }

  it("404s in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const res = await post("http://127.0.0.1:3005/api/devkit/validate", { text: VALID_TEXT });
    expect(res.status).toBe(404);
    vi.unstubAllEnvs();
  });

  it("404s off loopback in development", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await post("http://example.com/api/devkit/validate", { text: VALID_TEXT });
    expect(res.status).toBe(404);
    vi.unstubAllEnvs();
  });

  it("accepts valid YAML text", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await post("http://127.0.0.1:3005/api/devkit/validate", { text: VALID_TEXT });
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true, issues: [] });
    vi.unstubAllEnvs();
  });

  it("reports YAML syntax errors", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await post("http://127.0.0.1:3005/api/devkit/validate", { text: "version: [1,\n" });
    const body = (await res.json()) as { ok: boolean; issues: string[] };
    expect(body.ok).toBe(false);
    expect(body.issues[0]).toMatch(/^\(yaml\):/);
    vi.unstubAllEnvs();
  });

  it("reports schema violations (strict unknown keys, missing deployment)", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await post("http://127.0.0.1:3005/api/devkit/validate", {
      text: "version: 1\nbogus: true\n",
    });
    const body = (await res.json()) as { ok: boolean; issues: string[] };
    expect(body.ok).toBe(false);
    expect(body.issues.join("\n")).toMatch(/bogus|requires deployment/);
    vi.unstubAllEnvs();
  });

  it("validates parsed objects", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await post("http://127.0.0.1:3005/api/devkit/validate", {
      object: { version: 1, deployment: { slug: "x", backend: { type: "digigraph" } } },
    });
    expect(await res.json()).toEqual({ ok: true, issues: [] });
    vi.unstubAllEnvs();
  });

  it("400s without text or object", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await post("http://127.0.0.1:3005/api/devkit/validate", {});
    expect(res.status).toBe(400);
    vi.unstubAllEnvs();
  });

  it("returns the scoped deployment when scope is provided", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await post("http://127.0.0.1:3005/api/devkit/validate", {
      text: VALID_TEXT,
      scope: ["deployment"],
    });
    const body = (await res.json()) as {
      ok: boolean;
      issues: string[];
      deployment: { slug: string } | null;
    };
    expect(res.status).toBe(200);
    expect(body.ok).toBe(true);
    expect(body.issues).toEqual([]);
    expect(body.deployment?.slug).toBe("devkit-fixture");
    vi.unstubAllEnvs();
  });

  it("strips secrets from the scoped deployment", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await post("http://127.0.0.1:3005/api/devkit/validate", {
      text: `version: 1\ndeployment:\n  slug: secret-fixture\n  backend:\n    type: digigraph\n  token: disk-secret\n`,
      scope: ["deployment"],
    });
    const body = (await res.json()) as {
      ok: boolean;
      deployment: Record<string, unknown> | null;
    };
    expect(body.ok).toBe(true);
    expect(body.deployment).not.toHaveProperty("token");
    vi.unstubAllEnvs();
  });

  it("reports a missing hosts key for hosts scopes", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await post("http://127.0.0.1:3005/api/devkit/validate", {
      text: VALID_TEXT,
      scope: ["hosts", "nope.example"],
    });
    const body = (await res.json()) as { ok: boolean; issues: string[]; deployment: null };
    expect(body.ok).toBe(false);
    expect(body.deployment).toBeNull();
    expect(body.issues.join("\n")).toMatch(/hosts\/nope\.example/);
    vi.unstubAllEnvs();
  });

  it("400s on a non-string-array scope", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await post("http://127.0.0.1:3005/api/devkit/validate", {
      text: VALID_TEXT,
      scope: "deployment",
    });
    expect(res.status).toBe(400);
    vi.unstubAllEnvs();
  });
});
