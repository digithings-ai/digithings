import { describe, expect, it } from "vitest";
import { mergeTenants, resolveEmbedTenants, TENANTS_KV_KEY } from "./tenants-kv";

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
});
