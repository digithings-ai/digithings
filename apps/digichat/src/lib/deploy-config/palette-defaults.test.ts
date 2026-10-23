import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import { describe, expect, it } from "vitest";
import { TRACE_DENSITIES } from "@digithings/ui/chat/trace-spacing";
import { DensitySchema, type DigichatDeployment } from "./schema";
import { materializeDigichatConfig } from "./loader";

const configDir = resolve(__dirname, "../../../config");

/**
 * Existing deployments omit the new palette keys. Parsing them must land on
 * the same behaviour they ship today: default rhythm, medium effort, toolbar
 * on, scrollbars always, no named palette.
 */
const SHIPPED = [
  // Every per-client config at the top of config/ (the trial configs today).
  ...readdirSync(configDir).filter((name) => name.endsWith(".yaml")),
  "examples/occ-embed.yaml",
  "examples/digithings-ai-embed.yaml",
];

function deployments(doc: unknown, name: string): DigichatDeployment[] {
  const cfg = materializeDigichatConfig(doc, name);
  return [cfg.deployment, ...Object.values(cfg.hosts ?? {})].filter(
    (dep): dep is DigichatDeployment => dep != null,
  );
}

describe("shipped digichat deployments keep today's palette defaults", () => {
  it("locks density ids to the spacing module", () => {
    expect(DensitySchema.options).toEqual([...TRACE_DENSITIES]);
  });

  it.each(SHIPPED)("%s stays on the builtin defaults", (name) => {
    const doc = loadYaml(readFileSync(resolve(configDir, name), "utf8"));
    const deps = deployments(doc, name);
    expect(deps.length).toBeGreaterThan(0);
    for (const dep of deps) {
      expect(dep.features.density).toBe("default");
      expect(dep.features.effort).toBe("medium");
      expect(dep.chrome.toolbar).toBe(true);
      expect(dep.chrome.scrollbars).toBe("always");
      expect(dep.chrome.palette).toBeUndefined();
    }
  });
});
