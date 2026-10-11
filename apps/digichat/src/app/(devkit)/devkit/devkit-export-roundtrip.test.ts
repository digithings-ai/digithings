/**
 * DIG-2962: the YAML export must round-trip.
 *
 * "Round-trips" is bounded honestly. The export deliberately REPLACES every
 * secret scalar with a `${VAR}` placeholder and hands the values over in the
 * .env fragment, so a byte-identical round-trip of a SECRET-bearing config is
 * impossible by design. The true property, pinned here:
 *
 *   exported YAML  ->  parses  ->  satisfies the deployment schema
 *                  ->  projects to the SAME deployment as the source,
 *                     once the secret fields the export is allowed to blank
 *                     are stripped from both sides.
 *
 * Measured fact this file encodes: NO shipped config carries a live `token:` /
 * `consumeUrl:` scalar — the only matches in `apps/digichat/config` are two
 * explanatory comments. So over the nine shipped configs the export IS
 * byte-identical, and the substitution arm is pinned on an injected fixture
 * instead. Asserting the shipped set alone would have made every assertion
 * pass over an unchanged document.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { buildComposeBundle, detectExportSecrets } from "./devkit-export";
import { stripDeploymentSecrets, validateDevkitDraftText } from "@/lib/devkit-configs";

const CONFIG_ROOT = resolve(__dirname, "../../../../config");

/** Every shipped digichat config, with the scope devkit-configs.ts parses it under. */
const SHIPPED: Array<{ slug: string; rel: string; scope: string[] }> = [
  { slug: "local-app", rel: "examples/local-app.yaml", scope: ["deployment"] },
  { slug: "local-app", rel: "examples/local-app-memory.yaml", scope: ["deployment"] },
  { slug: "local-cli", rel: "examples/local-cli.yaml", scope: ["deployment"] },
  { slug: "digiquant-dashboard", rel: "examples/dashboard-modal.yaml", scope: ["deployment"] },
  { slug: "datatap", rel: "examples/datatap-mcp.yaml", scope: ["deployment"] },
  { slug: "datatap-trial-foundry", rel: "datatap-trial-foundry.yaml", scope: ["deployment"] },
  { slug: "datatap-trial-test", rel: "datatap-trial-test.yaml", scope: ["deployment"] },
  { slug: "occ", rel: "examples/occ-embed.yaml", scope: ["hosts", "occ.digithings.ai"] },
  { slug: "digithings-ai", rel: "examples/digithings-ai-embed.yaml", scope: ["hosts", "digithings.ai"] },
];

function read(rel: string): string {
  return readFileSync(resolve(CONFIG_ROOT, rel), "utf8");
}

/**
 * A shipped config with ONE secret scalar inserted. Exactly one, on purpose:
 * adding a second `gate:` beside the file's own would be a duplicate-key
 * document, so the `consumeUrl` arm gets its own minimal fixture below.
 */
function withInjectedToken(rel: string): string {
  const lines = read(rel).split("\n");
  const at = lines.findIndex((l) => /^deployment:\s*$/.test(l));
  if (at < 0) throw new Error(`no deployment: key in ${rel}`);
  lines.splice(at + 1, 0, "  token: fixture-deployment-token-value");
  return lines.join("\n");
}

const CONSUME_URL_FIXTURE = [
  "version: 1",
  "deployment:",
  "  slug: probe",
  "  backend:",
  "    type: digigraph",
  "  gate:",
  "    consumeUrl: https://example.invalid/consume?k=fixture",
].join("\n");

describe("YAML export round-trips", () => {
  it("covers every shipped config (control: the census is not empty)", () => {
    expect(SHIPPED.length).toBe(9);
    for (const cfg of SHIPPED) expect(read(cfg.rel).length).toBeGreaterThan(0);
  });

  describe("shipped configs", () => {
    for (const cfg of SHIPPED) {
      it(`${cfg.rel} exports a document that re-validates to the same deployment`, () => {
        const source = read(cfg.rel);
        const before = validateDevkitDraftText(source, cfg.scope);
        expect(before.ok, before.issues.join(" ")).toBe(true);
        expect(before.deployment).not.toBeNull();

        const exported = buildComposeBundle(cfg.slug, source);
        const after = validateDevkitDraftText(exported.configYaml, cfg.scope);
        expect(after.ok, after.issues.join(" ")).toBe(true);
        expect(stripDeploymentSecrets(after.deployment!)).toEqual(
          stripDeploymentSecrets(before.deployment!),
        );
      });
    }

    it("ships no live secret scalar, so the export is byte-identical there", () => {
      // This is the fact that makes the nine cases above honest rather than
      // vacuous — and it is pinned so a future secret-bearing config is a
      // deliberate change, not a silent drift away from this assertion.
      for (const cfg of SHIPPED) {
        expect(detectExportSecrets(read(cfg.rel))).toEqual([]);
        expect(buildComposeBundle(cfg.slug, read(cfg.rel)).configYaml).toBe(read(cfg.rel));
      }
    });
  });

  describe("a config carrying secrets", () => {
    it("re-validates to the same deployment with every secret blanked", () => {
      const source = withInjectedToken("examples/local-app.yaml");
      const before = validateDevkitDraftText(source, ["deployment"]);
      expect(before.ok, before.issues.join(" ")).toBe(true);

      const bundle = buildComposeBundle("local-app", source);
      expect(bundle.configYaml).toContain("token: ${DIGICHAT_EMBED_TOKEN}");
      expect(bundle.configYaml).not.toContain("fixture-deployment-token-value");
      expect(bundle.envFragment).toContain("DIGICHAT_EMBED_TOKEN=");

      const after = validateDevkitDraftText(bundle.configYaml, ["deployment"]);
      expect(after.ok, after.issues.join(" ")).toBe(true);
      expect(stripDeploymentSecrets(after.deployment!)).toEqual(
        stripDeploymentSecrets(before.deployment!),
      );
      // Non-vacuity: the equality above is over a POPULATED deployment, not an
      // empty-vs-empty pair — validateDevkitDraftText returns the secret-
      // stripped scoped deployment, so the stripped comparison is what proves
      // NON-secret fidelity, and the text assertions above prove no secret
      // value leaked. Assert both halves so neither can pass on its own.
      expect(before.deployment!.chrome).toBeDefined();
      expect(Object.keys(after.deployment!).length).toBeGreaterThan(3);
      expect(after.deployment!.token).toBeUndefined();
    });

    it("derives an MCP server variable from its id, or from its tokenEnv", () => {
      const yaml = [
        "version: 1",
        "deployment:",
        "  slug: probe",
        "  mcp:",
        "    servers:",
        "      - id: zammad",
        "        url: https://zammad.invalid/mcp",
        "        token: value-one",
        "      - id: vault",
        "        url: https://vault.invalid/mcp",
        "        tokenEnv: MCP_VAULT_TOKEN",
        "        token: value-two",
      ].join("\n");
      expect(detectExportSecrets(yaml).map((s) => [s.variable, s.context])).toEqual([
        ["ZAMMAD_TOKEN", "mcp server 'zammad'"],
        ["MCP_VAULT_TOKEN", "mcp server 'vault'"],
      ]);
      const bundle = buildComposeBundle("probe", yaml);
      expect(bundle.configYaml).toContain("token: ${ZAMMAD_TOKEN}");
      expect(bundle.configYaml).toContain("token: ${MCP_VAULT_TOKEN}");
      expect(bundle.envFragment).toContain("ZAMMAD_TOKEN=");
      expect(bundle.envFragment).toContain("MCP_VAULT_TOKEN=");
      expect(bundle.secrets).toHaveLength(2);
    });

    it("drops block-scalar continuation lines rather than emitting them", () => {
      const yaml = [
        "version: 1",
        "deployment:",
        "  slug: probe",
        "  token: |",
        "    line-one-of-a-block-scalar",
        "    line-two-of-a-block-scalar",
      ].join("\n");
      const bundle = buildComposeBundle("probe", yaml);
      expect(bundle.configYaml).toContain("token: ${DIGICHAT_EMBED_TOKEN}");
      expect(bundle.configYaml).not.toContain("line-one-of-a-block-scalar");
      expect(bundle.configYaml).not.toContain("line-two-of-a-block-scalar");
    });
  });
});

  describe("the consumeUrl arm", () => {
    it("blanks the quota URL into its own env var and round-trips", () => {
      const before = validateDevkitDraftText(CONSUME_URL_FIXTURE, ["deployment"]);
      expect(before.ok, before.issues.join(" ")).toBe(true);

      const bundle = buildComposeBundle("probe", CONSUME_URL_FIXTURE);
      expect(bundle.configYaml).toContain("consumeUrl: https://replace-me.invalid/consume");
      expect(bundle.configYaml).not.toContain("example.invalid/consume");
      expect(bundle.envFragment).toContain("DIGICHAT_CONSUME_URL=");

      const after = validateDevkitDraftText(bundle.configYaml, ["deployment"]);
      expect(after.ok, after.issues.join(" ")).toBe(true);
      expect(stripDeploymentSecrets(after.deployment!)).toEqual(
        stripDeploymentSecrets(before.deployment!),
      );
    });
  });
