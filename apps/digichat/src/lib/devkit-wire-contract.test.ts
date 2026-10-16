import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { listDevkitEntries } from "./devkit-configs";

/**
 * Behavioral pin on the server→client wire shape: the devkit menu consumes
 * `GET /api/devkit/configs` JSON directly, so every entry must survive a
 * JSON round-trip with the exact types the client narrows on. This is the
 * regression net for the T4 drift (server `issues: string[]` vs a stale
 * client assumption) — no source-string matching involved.
 */
describe("devkit wire contract", () => {
  it("round-trips entries with client-consumable types", () => {
    const dir = mkdtempSync(join(tmpdir(), "devkit-wire-"));
    mkdirSync(join(dir, "examples"), { recursive: true });
    writeFileSync(
      join(dir, "local.yaml"),
      `version: 1\ndeployment:\n  slug: wire\n  backend:\n    type: digigraph\n  token: wire-secret\n`,
    );
    writeFileSync(join(dir, "examples", "broken.yaml"), "version: [1,\n");

    const entries = listDevkitEntries(dir, {}, dir);
    const wire = JSON.parse(JSON.stringify({ entries })) as {
      entries: {
        id: string;
        kind: unknown;
        path: unknown;
        label: unknown;
        readOnly: unknown;
        ok: unknown;
        issues: unknown;
        redactedText: unknown;
        deployment: unknown;
      }[];
    };
    expect(wire.entries.length).toBe(2);
    for (const entry of wire.entries) {
      expect(typeof entry.id).toBe("string");
      expect(["file", "env"]).toContain(entry.kind);
      expect(typeof entry.path).toBe("string");
      expect(typeof entry.label).toBe("string");
      expect(typeof entry.readOnly).toBe("boolean");
      expect(typeof entry.ok).toBe("boolean");
      expect(Array.isArray(entry.issues)).toBe(true);
      for (const issue of entry.issues as unknown[]) expect(typeof issue).toBe("string");
      expect(
        entry.redactedText === null || typeof entry.redactedText === "string",
      ).toBe(true);
      expect(
        entry.deployment === null || typeof entry.deployment === "object",
      ).toBe(true);
    }
    const okEntry = wire.entries.find((e) => e.id === "file:local.yaml");
    expect(okEntry?.ok).toBe(true);
    expect(JSON.stringify(okEntry)).not.toContain("wire-secret");
    const broken = wire.entries.find((e) => e.id === "file:examples/broken.yaml");
    expect(broken?.ok).toBe(false);
    expect(broken?.deployment).toBeNull();
  });
});
