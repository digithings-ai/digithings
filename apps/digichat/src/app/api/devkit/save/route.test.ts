import { describe, expect, it, vi } from "vitest";

describe("POST /api/devkit/save", () => {
  async function post(url: string, body: unknown) {
    const { POST } = await import("./route");
    return POST(
      new Request(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    );
  }

  it("404s in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const res = await post("http://127.0.0.1:3005/api/devkit/save", { id: "x", text: "y" });
    expect(res.status).toBe(404);
    vi.unstubAllEnvs();
  });

  it("404s off loopback in development", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await post("https://example.com/api/devkit/save", { id: "x", text: "y" });
    expect(res.status).toBe(404);
    vi.unstubAllEnvs();
  });

  it("400s on a malformed body without touching the filesystem", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await post("http://127.0.0.1:3005/api/devkit/save", { id: "file:x.yaml" });
    expect(res.status).toBe(400);
    const body = (await res.json()) as { ok: boolean; issues: string[] };
    expect(body.ok).toBe(false);
    vi.unstubAllEnvs();
  });

  it("413s an oversized body", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await post("http://127.0.0.1:3005/api/devkit/save", {
      id: "file:x.yaml",
      text: "x".repeat(1_000_001),
    });
    expect(res.status).toBe(413);
    vi.unstubAllEnvs();
  });

  it("saves a valid draft end-to-end against a tmp config dir", async () => {
    const { mkdtempSync, writeFileSync, readFileSync, rmSync } = await import("node:fs");
    const { tmpdir } = await import("node:os");
    const { join } = await import("node:path");
    const dir = mkdtempSync(join(tmpdir(), "devkit-save-route-"));
    try {
      const seed = 'version: 1\ndeployment:\n  slug: route-proof\n  backend:\n    type: digigraph\n';
      writeFileSync(join(dir, "route-proof.yaml"), seed);
      vi.stubEnv("NODE_ENV", "development");
      vi.stubEnv("DEVKIT_CONFIG_DIR", dir);
      const edited = seed.replace("slug: route-proof", "slug: route-proof") + "  # touched\n";
      const res = await post("http://127.0.0.1:3005/api/devkit/save", {
        id: "file:route-proof.yaml",
        text: edited,
      });
      expect(res.status).toBe(200);
      const body = (await res.json()) as { ok: boolean; backup: string | null };
      expect(body.ok).toBe(true);
      expect(body.backup).toBe("route-proof.yaml.bak");
      expect(readFileSync(join(dir, "route-proof.yaml"), "utf8")).toBe(edited);
      expect(readFileSync(join(dir, "route-proof.yaml.bak"), "utf8")).toBe(seed);
    } finally {
      vi.unstubAllEnvs();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
