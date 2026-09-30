import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEVKIT_SENTINEL } from "@/lib/devkit-configs";

type WireEntry = {
  id: string;
  kind: "file" | "env";
  path: string;
  label: string;
  readOnly: boolean;
  ok: boolean;
  issues: string[];
  redactedText: string | null;
  deployment: Record<string, unknown> | null;
};

const SECRET_LINE_PATTERN = /^\s*["']?(token|consumeUrl)["']?\s*:(.*)$/;

describe("GET /api/devkit/configs", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  async function get(url: string) {
    const { GET } = await import("./route");
    return GET(new Request(url));
  }

  it("404s in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const res = await get("http://127.0.0.1:3005/api/devkit/configs");
    expect(res.status).toBe(404);
    vi.unstubAllEnvs();
  });

  it("404s off loopback in development", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await get("http://example.com/api/devkit/configs");
    expect(res.status).toBe(404);
    vi.unstubAllEnvs();
  });

  it("serves entries with no secret bytes at HTTP level", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const res = await get("http://127.0.0.1:3005/api/devkit/configs");
    expect(res.status).toBe(200);
    const body = (await res.json()) as { entries: WireEntry[] };
    expect(Array.isArray(body.entries)).toBe(true);
    expect(body.entries.length).toBeGreaterThan(0);
    for (const entry of body.entries) {
      // Every secret-looking line in served text holds only the sentinel.
      if (typeof entry.redactedText === "string") {
        for (const line of entry.redactedText.split("\n")) {
          const match = SECRET_LINE_PATTERN.exec(line);
          if (match) expect(match[2].trim()).toBe(DEVKIT_SENTINEL);
        }
      }
      // Served deployments carry no secret fields or operator setup maps.
      const dep = entry.deployment;
      if (dep) {
        expect(dep).not.toHaveProperty("token");
        expect(dep.gate as Record<string, unknown> | undefined).not.toHaveProperty(
          "consumeUrl",
        );
        const servers = (dep.mcp as { servers?: Record<string, unknown>[] } | undefined)
          ?.servers;
        for (const server of servers ?? []) {
          expect(server).not.toHaveProperty("token");
          expect(server).not.toHaveProperty("setup");
        }
      }
    }
    vi.unstubAllEnvs();
  });
});
