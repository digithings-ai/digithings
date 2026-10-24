import { describe, expect, it } from "vitest";
import {
  CONFIG_KV_KEY,
  mergeTenants,
  resolveConfigYaml,
  resolveEmbedTenants,
  TENANTS_KV_KEY,
} from "./tenants-kv";

const env = { OCC_INVITE_KEY: "invite-123", MCP_EDGE_KEY: "edge-456" };
const kvCfg = {
  "occ.digithings.ai": {
    slug: "occ",
    tokenEnv: "OCC_INVITE_KEY",
    webSearch: false,
    mcp: { servers: [{ id: "zammad", url: "https://graph.example/_stack/mcp/zammad/mcp", tokenEnv: "MCP_EDGE_KEY", authHeader: "x-digi-mcp-key", allowedTools: ["get_ticket"], mutatingTools: [] }] },
  },
};
const legacy = {
  "occ.digithings.ai": { slug: "occ", token: "old", webSearch: true },
  "digiquant.io": { slug: "digiquant", token: "dq" },
};

describe("mergeTenants", () => {
  it("resolves tenant and MCP tokenEnv refs from secrets", () => {
    const r = mergeTenants(JSON.stringify(kvCfg), undefined, env);
    const occ = JSON.parse(r.json)["occ.digithings.ai"];
    expect(occ.token).toBe("invite-123");
    expect(occ.tokenEnv).toBeUndefined();
    expect(occ.mcp.servers[0].token).toBe("edge-456");
    expect(occ.mcp.servers[0].tokenEnv).toBeUndefined();
    expect(r.source).toBe("kv");
  });

  it("KV host wins, legacy-only hosts are kept", () => {
    const r = mergeTenants(JSON.stringify(kvCfg), JSON.stringify(legacy), env);
    const all = JSON.parse(r.json);
    expect(all["occ.digithings.ai"].webSearch).toBe(false);
    expect(all["digiquant.io"].token).toBe("dq");
    expect(r.source).toBe("merged");
  });

  it("unresolved ref keeps the legacy entry and reports names only", () => {
    const r = mergeTenants(JSON.stringify(kvCfg), JSON.stringify(legacy), { MCP_EDGE_KEY: "x" });
    expect(JSON.parse(r.json)["occ.digithings.ai"].token).toBe("old");
    expect(r.unresolved).toEqual({ "occ.digithings.ai": ["OCC_INVITE_KEY"] });
  });

  it("unresolved ref with no legacy entry drops the host (fail closed)", () => {
    const r = mergeTenants(JSON.stringify(kvCfg), undefined, {});
    expect(r.json).toBe("");
  });

  it("invalid KV falls back to the legacy secret", () => {
    const r = mergeTenants("not json", JSON.stringify(legacy), env);
    expect(r.source).toBe("legacy");
    expect(JSON.parse(r.json)["digiquant.io"].slug).toBe("digiquant");
  });

  it("invalid legacy secret does not throw and the KV config still serves", () => {
    const r = mergeTenants(JSON.stringify(kvCfg), "not json", env);
    expect(r.source).toBe("kv");
    expect(JSON.parse(r.json)["occ.digithings.ai"].token).toBe("invite-123");
  });

  it("invalid legacy secret with no usable KV fails closed to no tenants", () => {
    const r = mergeTenants("not json", "not json", env);
    expect(r.json).toBe("");
    expect(r.source).toBe("none");
  });

  it("ignores non-secret-shaped env names", () => {
    const bad = { h: { tokenEnv: "lower_case" } };
    const r = mergeTenants(JSON.stringify(bad), undefined, { lower_case: "v" });
    expect(r.unresolved).toEqual({ h: ["lower_case"] });
  });
});

describe("resolveEmbedTenants", () => {
  it("reads the KV key and survives KV errors", async () => {
    const kv = { get: async (k: string) => (k === TENANTS_KV_KEY ? JSON.stringify(kvCfg) : null) };
    expect((await resolveEmbedTenants(kv, undefined, env)).source).toBe("kv");
    const broken = { get: async () => { throw new Error("down"); } };
    expect((await resolveEmbedTenants(broken, JSON.stringify(legacy), env)).source).toBe("legacy");
    expect((await resolveEmbedTenants(undefined, undefined, env)).source).toBe("none");
  });

  it("survives an invalid legacy secret", async () => {
    const kv = { get: async (k: string) => (k === TENANTS_KV_KEY ? JSON.stringify(kvCfg) : null) };
    expect((await resolveEmbedTenants(kv, "not json", env)).source).toBe("kv");
    expect((await resolveEmbedTenants(undefined, "not json", env)).source).toBe("none");
  });
});

/**
 * The deployment document lives in the same KV namespace under `config-yaml`,
 * so it can be edited without redeploying either the Worker or the image.
 */
describe("resolveConfigYaml", () => {
  it("reads the document from the config-yaml key", async () => {
    const doc = "version: 1\ndeployment:\n  slug: occ\n";
    const kv = { get: async (k: string) => (k === CONFIG_KV_KEY ? doc : null) };
    await expect(resolveConfigYaml(kv)).resolves.toEqual({ yaml: doc, source: "kv" });
    // Same namespace as the tenant registry, different key.
    expect(CONFIG_KV_KEY).toBe("config-yaml");
    expect(CONFIG_KV_KEY).not.toBe(TENANTS_KV_KEY);
  });

  it("treats a missing key, an empty value or a missing binding as none", async () => {
    const missing = { get: async () => null };
    const blank = { get: async () => "  \n" };
    await expect(resolveConfigYaml(missing)).resolves.toEqual({ yaml: "", source: "none" });
    await expect(resolveConfigYaml(blank)).resolves.toEqual({ yaml: "", source: "none" });
    await expect(resolveConfigYaml(undefined)).resolves.toEqual({ yaml: "", source: "none" });
  });

  it("leaves the container on its file/defaults when the KV read fails", async () => {
    const broken = { get: async () => { throw new Error("down"); } };
    await expect(resolveConfigYaml(broken)).resolves.toEqual({ yaml: "", source: "none" });
  });
});
