/**
 * The naming contract (#tool-contract).
 *
 * Every other tooling test compares config → config or config → UI, so a
 * document that names a tool nobody exposes passes all of them and fails at
 * the model. This test closes that gap: it loads every deployment document
 * that ships, applies digigraph's two exposure rules, and asserts that every
 * id a document names exists in the set that tenant can actually call.
 *
 * The two rules, both read off digigraph:
 *
 *  - native `digisearch` / `digisearch_fetch_all` are hidden once the tenant
 *    sets its own per-index search tools (graph/research.py:489-513);
 *  - an MCP row with no `allowedTools` exposes none of the tools its server
 *    advertises (orchestration/mcp_client.py:734-753), so a row that names
 *    none is a row that can never be called.
 *
 * The advertised names come from `__fixtures__/mcp-surface.json`, which is
 * reviewed against each server's own source. Nothing here is inferred from a
 * label, a slug or a config — a name either exists on the server or it does
 * not.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { load as loadYaml } from "js-yaml";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../../..");

type SurfaceFile = {
  _private_surface?: string;
  _unvalidated_servers?: string[];
} & Record<string, unknown>;

/**
 * The house surface, plus the surface of the tenant servers the repo keeps
 * private. Client tool names do not go into the public fixture: the R0
 * literals gate (`scripts/check_r0_no_client_literals.py`) refuses them, so
 * the private half sits next to the deployment documents it belongs to and is
 * loaded by path from here.
 */
function loadSurface(): { advertised: Record<string, readonly string[]>; unvalidated: string[] } {
  const house = JSON.parse(
    readFileSync(join(here, "__fixtures__/mcp-surface.json"), "utf8"),
  ) as SurfaceFile;
  const privatePath = join(repoRoot, String(house._private_surface));
  const privateSurface = JSON.parse(readFileSync(privatePath, "utf8")) as SurfaceFile;
  const advertised: Record<string, readonly string[]> = {};
  for (const file of [house, privateSurface]) {
    for (const [key, value] of Object.entries(file)) {
      if (key.startsWith("_") || !Array.isArray(value)) continue;
      advertised[key] = value as string[];
    }
  }
  return {
    advertised,
    unvalidated: [...(privateSurface._unvalidated_servers ?? [])],
  };
}

const { advertised: SURFACE, unvalidated: UNVALIDATED } = loadSurface();

/** The names a server advertises, or the empty list when it is not reviewed. */
function advertises(serverId: string): readonly string[] | undefined {
  return SURFACE[serverId];
}

/**
 * The catalog id → orchestrator tool names digigraph's tool policy maps
 * (digigraph/src/digigraph/tool_policy.py `_DISABLE_TOOL_ALIASES`). A catalog
 * row is a group, and a group resolves when at least one of the names it
 * stands for is callable.
 */
const CATALOG_GROUPS: Record<string, readonly string[]> = {
  digisearch: ["digisearch", "digisearch_fetch_all"],
  search: ["digisearch", "digisearch_fetch_all"],
  digivault: ["digivault_search_notes", "digivault_get_note"],
  vault: ["digivault_search_notes", "digivault_get_note"],
  docs: ["digivault_search_notes", "digivault_get_note"],
};

type ServerRow = {
  id: string;
  allowedTools?: unknown;
  default?: boolean;
};

type TenantNode = {
  backend?: { type?: string; digisearchTools?: unknown; digisearch_tools?: unknown };
  tools?: { catalog?: Array<{ id?: string; tools?: Array<{ id?: string }> }> };
  mcp?: { servers?: ServerRow[] };
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Objects merge, arrays and scalars replace — the shape a YAML `extends` takes. */
function merge(base: unknown, over: unknown): unknown {
  if (!isRecord(base) || !isRecord(over)) return over === undefined ? base : over;
  const out: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(over)) {
    out[key] = key in base ? merge(base[key], value) : value;
  }
  return out;
}

function walkYaml(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walkYaml(full));
    else if (/\.ya?ml$/.test(entry)) out.push(full);
  }
  return out;
}

/** The `.yaml` files directly in `dir`, not its subdirectories. */
function listYaml(dir: string): string[] {
  return readdirSync(dir)
    .filter((entry) => /\.ya?ml$/.test(entry))
    .map((entry) => join(dir, entry));
}

const DOCUMENTS: string[] = [
  ...listYaml(join(repoRoot, "apps/digichat/config")),
  ...walkYaml(join(repoRoot, "apps/digichat/config/examples")),
  ...walkYaml(join(repoRoot, "apps/digichat/config/overrides")),
  "infra/digichat-release/config/digichat.yaml.example",
].map((path) => (path.startsWith("/") ? path : join(repoRoot, path)));

const OVERLAYS: string[] = ["DIG-3556-staged-prod-tenant-config.json", "DIG-4488-tenant-overlay.json"].map(
  (name) => join(repoRoot, "infra/digichat-release", name),
);

type Tenant = { document: string; where: string; node: TenantNode };

function yamlTenants(path: string): Tenant[] {
  const doc = loadYaml(readFileSync(path, "utf8"));
  if (!isRecord(doc)) return [];
  const document = path.slice(repoRoot.length + 1);
  const extendsDefaults = doc.extends === "defaults";
  const defaults = extendsDefaults
    ? (loadYaml(
        readFileSync(join(repoRoot, "apps/digichat/config/defaults.yaml"), "utf8"),
      ) as Record<string, unknown>)
    : undefined;
  const baseNode = defaults ? (defaults.deployment as TenantNode) : undefined;
  const deployment = (extendsDefaults
    ? merge(baseNode, doc.deployment)
    : doc.deployment) as TenantNode | undefined;
  const tenants: Tenant[] = [];
  if (deployment) tenants.push({ document, where: "deployment", node: deployment });
  if (isRecord(doc.hosts)) {
    for (const [host, hostNode] of Object.entries(doc.hosts)) {
      if (!isRecord(hostNode)) continue;
      const merged = (deployment ? merge(deployment, hostNode) : hostNode) as TenantNode;
      tenants.push({ document, where: `hosts.${host}`, node: merged });
    }
  }
  return tenants;
}

function overlayTenants(path: string): Tenant[] {
  const doc = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
  const document = path.slice(repoRoot.length + 1);
  const registry = doc.DIGICHAT_EMBED_TENANTS;
  if (!isRecord(registry)) return [];
  return Object.entries(registry)
    .filter(([, value]) => isRecord(value))
    .map(([host, value]) => ({
      document,
      where: `DIGICHAT_EMBED_TENANTS.${host}`,
      node: value as TenantNode,
    }));
}

const TENANTS: Tenant[] = [
  ...DOCUMENTS.flatMap(yamlTenants),
  ...OVERLAYS.flatMap(overlayTenants),
].filter((tenant) => {
  // A Foundry agent owns its own tool list; digigraph's rules do not apply.
  const type = tenant.node.backend?.type;
  return type === undefined || type === "digigraph";
});

function serversOf(node: TenantNode): ServerRow[] {
  return (node.mcp?.servers ?? []).filter(
    (row): row is ServerRow => isRecord(row) && typeof row.id === "string",
  );
}

/**
 * The names this tenant can call: the native tools, minus the generic
 * digisearch pair when the tenant binds its own per-index tools, plus the
 * prefixed form of every tool an MCP row actually grants.
 */
function effectiveSet(node: TenantNode): Set<string> {
  const effective = new Set<string>(SURFACE.native ?? []);
  const bound = node.backend?.digisearchTools ?? node.backend?.digisearch_tools;
  if (isRecord(bound) && Object.keys(bound).length > 0) {
    effective.delete("digisearch");
    effective.delete("digisearch_fetch_all");
    for (const name of Object.keys(bound)) effective.add(name);
  }
  for (const server of serversOf(node)) {
    const advertised = advertises(server.id);
    if (!advertised) continue;
    const allowed = server.allowedTools;
    if (!Array.isArray(allowed) || allowed.length === 0) continue;
    for (const tool of allowed) {
      if (typeof tool === "string" && tool.trim()) {
        effective.add(`${server.id}_${tool.trim()}`.toLowerCase());
      }
    }
  }
  return effective;
}

type Problem = { document: string; where: string; server: string; id: string; reason: string };

function problemsIn(tenant: Tenant): Problem[] {
  const { document, where, node } = tenant;
  const problems: Problem[] = [];
  const effective = effectiveSet(node);

  for (const server of serversOf(node)) {
    const advertised = advertises(server.id);
    if (!advertised) continue;
    const allowed = server.allowedTools;
    if (!Array.isArray(allowed) || allowed.length === 0) {
      // digigraph denies every advertised tool on a row that names none, so
      // the row renders in `/tools` and can never be called.
      problems.push({
        document,
        where,
        server: server.id,
        id: "(none)",
        reason: `names no allowedTools, so digigraph refuses all ${advertised.length} advertised tools (mcp_client.py:734-753)`,
      });
      continue;
    }
    for (const tool of allowed) {
      if (typeof tool !== "string" || !advertised.includes(tool)) {
        problems.push({
          document,
          where,
          server: server.id,
          id: String(tool),
          reason: `is not a tool ${server.id} advertises (advertises: ${advertised.join(", ")})`,
        });
      }
    }
  }

  for (const row of node.tools?.catalog ?? []) {
    const rowId = typeof row.id === "string" ? row.id.trim() : "";
    if (!rowId) continue;
    for (const tool of row.tools ?? []) {
      const id = typeof tool.id === "string" ? tool.id.trim() : "";
      if (id && !effective.has(id)) {
        problems.push({
          document,
          where,
          server: rowId,
          id,
          reason: "is not a callable tool for this tenant",
        });
      }
    }
    const group = CATALOG_GROUPS[rowId] ?? [rowId];
    const resolvable =
      group.some((name) => effective.has(name)) ||
      [...effective].some((name) => name.startsWith(`${rowId}_`));
    if (!resolvable) {
      problems.push({
        document,
        where,
        server: rowId,
        id: rowId,
        reason: `names a catalog row that expands to nothing callable (tried: ${group.join(", ")})`,
      });
    }
  }

  return problems;
}

function describeProblem(problem: Problem): string {
  return `${problem.document} [${problem.where}] server "${problem.server}": id "${problem.id}" ${problem.reason}`;
}

describe("the shipped tool surface is callable (#tool-contract)", () => {
  it("loads the documents under test", () => {
    // A sweep that silently found nothing would read as a pass. Pin the shape.
    expect(DOCUMENTS.length).toBeGreaterThanOrEqual(15);
    expect(OVERLAYS.length).toBe(2);
    expect(TENANTS.length).toBeGreaterThanOrEqual(15);
  });

  it("never names a tool the tenant cannot call", () => {
    const problems = TENANTS.flatMap(problemsIn);
    const unique = [...new Set(problems.map(describeProblem))].sort();
    expect(unique.join("\n")).toBe("");
  });

  it("keeps the servers it does not validate on a reviewed list", () => {
    // Servers with no entry in the fixture are not validated, so the hole is
    // pinned: a server that appears in a shipped document and is not on this
    // list turns the test red. The list lives in the fixture, next to the
    // surface it is a gap in.
    const unknown = new Set<string>();
    for (const tenant of TENANTS) {
      for (const server of serversOf(tenant.node)) {
        if (!advertises(server.id)) unknown.add(server.id);
      }
    }
    expect([...unknown].sort()).toEqual([...UNVALIDATED].sort());
  });
});
