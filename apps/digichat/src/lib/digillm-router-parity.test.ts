import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { decideDigillmRoute } from "@/lib/digillm-router-engine";
import type { DigillmRouterRouteInput } from "@/lib/digillm-router";

import casesFile from "../../../../digillm/src/digillm/router/parity_cases.json";
import expectedFile from "../../../../digillm/src/digillm/router/parity_expected.json";

type ParityCase = {
  name: string;
  text: string;
  allowed: string[];
  fallback: string;
  routes?: DigillmRouterRouteInput[];
};

type ExpectedDecision = {
  name: string;
  route_id: string;
  label: string;
  model: string;
  reason: string;
  confidence: number;
};

const cases = casesFile.cases as ParityCase[];
const expected = new Map(
  (expectedFile.cases as ExpectedDecision[]).map((item) => [item.name, item]),
);

function repoRoot(): string {
  let dir = process.cwd();
  for (let hop = 0; hop < 5; hop += 1) {
    if (existsSync(path.join(dir, "digillm", "src", "digillm", "router", "__main__.py"))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error("digillm router package not found from cwd");
}

function pythonBin(root: string): string | undefined {
  const candidates = [path.join(root, ".venv", "bin", "python"), "python3"];
  for (const bin of candidates) {
    if (bin.includes(path.sep) && !existsSync(bin)) continue;
    try {
      execFileSync(bin, ["-c", "import pydantic, digillm.router"], {
        env: {
          ...process.env,
          PYTHONPATH: path.join(root, "digillm", "src"),
        },
        stdio: "ignore",
      });
      return bin;
    } catch {
      // This runtime cannot import the Python router. The golden file still binds CI.
    }
  }
  return undefined;
}

const ROOT = repoRoot();
const PYTHON = pythonBin(ROOT);

describe("digillm router parity", () => {
  it("keeps the scorer free of a filesystem or a process spawn", () => {
    const source = readFileSync(
      path.join(ROOT, "apps", "digichat", "src", "lib", "digillm-router-engine.ts"),
      "utf8",
    );
    expect(source).not.toContain("node:fs");
    expect(source).not.toContain("node:child_process");
    expect(source).not.toContain("cheaperinference");
  });

  it("matches the python golden on the fixed prompt set", () => {
    expect(expected.size).toBe(cases.length);
    for (const item of cases) {
      const want = expected.get(item.name);
      expect(want, item.name).toBeDefined();
      const decision = decideDigillmRoute({
        text: item.text,
        allowed: item.allowed,
        fallback: item.fallback,
        ...(item.routes ? { routes: item.routes } : {}),
      });
      expect(decision.routeId, item.name).toBe(want?.route_id);
      expect(decision.label, item.name).toBe(want?.label);
      expect(decision.model, item.name).toBe(want?.model);
      expect(decision.reason, item.name).toBe(want?.reason);
      expect(Math.abs(decision.confidence - (want?.confidence ?? 0)), item.name).toBeLessThan(
        1e-9,
      );
    }
  });

  it.skipIf(!PYTHON)("matches a live python process on the fixed prompt set", () => {
    const bin = PYTHON;
    if (!bin) return;
    for (const item of cases) {
      const stdout = execFileSync(bin, ["-m", "digillm.router"], {
        input: JSON.stringify({
          text: item.text,
          allowed: item.allowed,
          fallback: item.fallback,
          ...(item.routes ? { routes: item.routes } : {}),
        }),
        encoding: "utf8",
        env: {
          ...process.env,
          PYTHONPATH: path.join(ROOT, "digillm", "src"),
        },
      });
      const parsed = JSON.parse(stdout) as {
        route_id: string;
        label: string;
        model: string;
        reason: string;
        confidence: number;
      };
      const decision = decideDigillmRoute({
        text: item.text,
        allowed: item.allowed,
        fallback: item.fallback,
        ...(item.routes ? { routes: item.routes } : {}),
      });
      expect(decision.routeId, item.name).toBe(parsed.route_id);
      expect(decision.model, item.name).toBe(parsed.model);
      expect(decision.reason, item.name).toBe(parsed.reason);
      expect(decision.label, item.name).toBe(parsed.label);
      expect(Math.abs(decision.confidence - parsed.confidence), item.name).toBeLessThan(1e-9);
    }
  }, 30_000);
});
