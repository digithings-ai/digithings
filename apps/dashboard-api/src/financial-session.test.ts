import { describe, expect, it, vi } from "vitest";
import {
  APP_DATA_PATHS,
  LUXALGO_TOOLS,
  buildFinancialSession,
  forwardFinancialTurn,
  loadFinancialSession,
  parseTenantConfig,
  type FinancialSessionEnv,
} from "./financial-session";

const TENANT = {
  slug: "digiquant",
  cheapModel: "groq/llama-3.1-8b-instant",
  digichatOrigin: "https://chat.example.test/ignored",
  gloomberbTools: ["digifetch_quote"],
};

const KEY = "cheap-key-sentinel";

function env(raw: unknown, key: string | null = KEY): FinancialSessionEnv {
  return {
    ...(key ? { DIGICHAT_CHEAP_INFERENCE_KEY: key } : {}),
    DIGICHAT_TENANT: { get: async () => (raw === null ? null : JSON.stringify(raw)) },
  };
}

describe("financial digichat session", () => {
  it("stays closed without a cheap key or a KV tenant record", async () => {
    expect(await loadFinancialSession(env(TENANT, ""), "baseline")).toBeNull();
    expect(await loadFinancialSession(env(TENANT, null), "baseline")).toBeNull();
    expect(await loadFinancialSession({ DIGICHAT_CHEAP_INFERENCE_KEY: KEY }, "baseline")).toBeNull();
    expect(await loadFinancialSession(env(null), "baseline")).toBeNull();
  });

  it("refuses a tenant record that carries a secret field or a non-https origin", () => {
    expect(parseTenantConfig(JSON.stringify({ ...TENANT, token: "nope" }))).toBeNull();
    expect(parseTenantConfig(JSON.stringify({ ...TENANT, digichatOrigin: "http://chat.example.test" }))).toBeNull();
    expect(parseTenantConfig("{")).toBeNull();
  });

  it("builds a desk-scoped session with LuxAlgo tools, Gloomberb tools, and app paths", async () => {
    const baseline = await loadFinancialSession(env(TENANT), "baseline");
    const fx = await loadFinancialSession(env({ ...TENANT, gloomberbTools: [] }), "fx");
    expect(baseline?.session).toMatchObject({
      id: "fin-baseline",
      desk: "baseline",
      context: "baseline desk run",
      cheapModel: TENANT.cheapModel,
      tools: {
        gloomberb: ["digifetch_quote"],
        luxalgo: [...LUXALGO_TOOLS],
        app: [...APP_DATA_PATHS.baseline],
      },
    });
    expect(fx?.session.context).toBe("FX Hub");
    expect(fx?.session.tools.app).toEqual([...APP_DATA_PATHS.fx]);
    expect(fx?.session.tools.gloomberb).toEqual([]);
    const published = { session: baseline?.session, config: baseline?.config };
    expect(JSON.stringify(published)).not.toContain(KEY);
    expect(buildFinancialSession(parseTenantConfig(JSON.stringify(TENANT))!, "baseline").tools.luxalgo).toContain(
      "luxalgo_library_search",
    );
  });

  it("forwards a turn with the cheap key on the header only", async () => {
    const loaded = await loadFinancialSession(env(TENANT), "fx");
    expect(loaded).not.toBeNull();
    const fetchFn = vi.fn(async () => Response.json({ reply: "FX Hub book" }));
    const out = await forwardFinancialTurn(loaded!.config, loaded!.inferenceKey, loaded!.session, "levels?", fetchFn);
    expect(out).toEqual({ reply: "FX Hub book" });
    expect(fetchFn).toHaveBeenCalledOnce();
    const [url, init] = fetchFn.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe("https://chat.example.test/api/chat");
    const headers = init.headers as Record<string, string>;
    expect(headers.authorization).toBe(`Bearer ${KEY}`);
    const body = String(init.body);
    expect(body).not.toContain(KEY);
    expect(body).toContain("FX Hub");
    expect(body).toContain("luxalgo_library_search");
    expect(body).toContain("digifetch_quote");
    expect(body).toContain("/fx/pairs");
  });
});
