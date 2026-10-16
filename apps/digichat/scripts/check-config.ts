/**
 * Validate a digichat deployment config and print what it resolves to.
 *
 *   make digichat-config-check CONFIG=infra/digichat-release/config/digichat.yaml
 *
 * Fails loudly on a missing file, invalid YAML/JSON, or a schema violation —
 * the container would otherwise fall back to the built-in dev default and the
 * misconfiguration would be invisible. Secrets are never printed (the token and
 * MCP URLs are stripped by the client projection).
 */
import { DEFAULT_CONFIG_PATH, loadDigichatConfig } from "../src/lib/deploy-config/loader";
import { toDigichatClientConfig } from "../src/lib/deploy-config/client-projection";

const requested = process.argv[2]?.trim();
const path = requested || process.env.DIGICHAT_CONFIG_PATH?.trim() || DEFAULT_CONFIG_PATH;
process.env.DIGICHAT_CONFIG_PATH = path;

function field(label: string, value: unknown): string {
  return `  ${label.padEnd(14)} ${value === undefined || value === "" ? "—" : String(value)}`;
}

try {
  const cfg = loadDigichatConfig({ allowMissingFile: false });
  const mergedTenants = Boolean(process.env.DIGICHAT_EMBED_TENANTS?.trim());

  const deployments: Array<[string, typeof cfg.deployment]> = [];
  if (cfg.deployment) deployments.push(["deployment", cfg.deployment]);
  for (const [host, dep] of Object.entries(cfg.hosts ?? {})) deployments.push([host, dep]);

  console.log(`digichat config OK — ${path}`);
  console.log(field("version", cfg.version));
  console.log(field("shape", cfg.deployment && cfg.hosts ? "deployment + hosts" : cfg.hosts ? "hosts" : "deployment"));
  console.log(field("deployments", deployments.length));
  if (mergedTenants) console.log(field("tenants env", "merged (DIGICHAT_EMBED_TENANTS)"));

  for (const [label, dep] of deployments) {
    if (!dep) continue;
    const client = toDigichatClientConfig(dep);
    console.log(`\n[${label}]`);
    console.log(field("slug", dep.slug));
    console.log(field("chrome", `${dep.chrome.mode} / ${dep.chrome.theme} / ${dep.chrome.skin}`));
    console.log(field("title", dep.chrome.title));
    console.log(field("welcome", dep.chrome.welcome?.title ?? dep.chrome.welcome));
    console.log(field("persistence", dep.persistence));
    console.log(field("auth", dep.auth));
    console.log(field("backend", dep.backend.type));
    console.log(field("models", client.models.available.length ? `${client.models.available.length} available` : "backend default"));
    console.log(field("tools", client.tools.catalog.length ? client.tools.catalog.map((t) => t.id).join(", ") : "none"));
    console.log(field("mcp", client.mcp.servers.length ? client.mcp.servers.map((s) => s.id).join(", ") : "none"));
    console.log(field("gate", `${dep.gate.mode}${dep.gate.webSearch ? " +web" : ""}${dep.gate.showByok ? " +byok" : ""}`));
    console.log(field("token", dep.token ? "set" : "unset"));
  }
} catch (err) {
  console.error(`digichat config INVALID — ${path}`);
  console.error(`  ${err instanceof Error ? err.message : String(err)}`);
  console.error("\n  Reference configs: apps/digichat/config/examples/");
  console.error("  Copy the starter:  cp infra/digichat-release/config/digichat.yaml.example infra/digichat-release/config/digichat.yaml");
  process.exit(1);
}
