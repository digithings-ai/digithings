import { describe, expect, it, vi } from "vitest";
import {
  APP_DATA_PATHS,
  LUXALGO_TOOLS,
  buildFinancialSession,
  forwardFinancialTurn,
  loadFinancialSession,
  parseTenantConfig,
  readStreamReply,
  type FinancialSessionEnv,
} from "./financial-session";

const TENANT = {
  slug: "digiquant",
  cheapModel: "groq/llama-3.1-8b-instant",
  digichatOrigin: "https://chat.digithings.ai/ignored",
  gloomberbTools: ["gloomberb_quote"],
};

const KEY = "digi_live_machine-key-sentinel";

/** An AI SDK UI-message stream, as `createUIMessageStreamResponse` writes it. */
function uiStream(chunks: unknown[]): Response {
  const body = [...chunks.map((c) => `data: ${JSON.stringify(c)}`), "data: [DONE]"].join("\n\n") + "\n\n";
  return new Response(body, { headers: { "content-type": "text/event-stream" } });
}

function env(raw: unknown, key: string | null = KEY): FinancialSessionEnv {
  return {
    ...(key ? { DIGICHAT_MACHINE_KEY: key } : {}),
    DIGICHAT_TENANT: { get: async () => (raw === null ? null : JSON.stringify(raw)) },
  };
}

describe("financial digichat session", () => {
  it("stays closed without a digichat machine key or a KV tenant record", async () => {
    expect(await loadFinancialSession(env(TENANT, ""), "baseline")).toBeNull();
    expect(await loadFinancialSession(env(TENANT, null), "baseline")).toBeNull();
    expect(await loadFinancialSession(env(TENANT, "sk-provider-key"), "baseline")).toBeNull();
    expect(await loadFinancialSession(env(TENANT, "digi_live_"), "baseline")).toBeNull();
    expect(await loadFinancialSession({ DIGICHAT_MACHINE_KEY: KEY }, "baseline")).toBeNull();
    expect(await loadFinancialSession(env(null), "baseline")).toBeNull();
  });

  it("refuses a secret field, a non-house or non-https origin, or a non-Gloomberb tool name", () => {
    expect(parseTenantConfig(JSON.stringify({ ...TENANT, token: "nope" }))).toBeNull();
    expect(parseTenantConfig(JSON.stringify({ ...TENANT, digichatOrigin: "http://chat.digithings.ai" }))).toBeNull();
    expect(parseTenantConfig(JSON.stringify({ ...TENANT, digichatOrigin: "https://chat.example.test" }))).toBeNull();
    expect(parseTenantConfig(JSON.stringify({ ...TENANT, digichatOrigin: "https://digithings.ai.example.test" }))).toBeNull();
    expect(parseTenantConfig(JSON.stringify({ ...TENANT, gloomberbTools: ["digifetch_quote"] }))).toBeNull();
    expect(parseTenantConfig(JSON.stringify({ ...TENANT, digichatOrigin: "http://127.0.0.1:3000" }))?.digichatOrigin).toBe(
      "http://127.0.0.1:3000",
    );
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
        gloomberb: ["gloomberb_quote"],
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

  it("forwards one UIMessage to the digichat BFF with the machine key on the header only", async () => {
    const loaded = await loadFinancialSession(env(TENANT), "fx");
    expect(loaded).not.toBeNull();
    const fetchFn = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      uiStream([
        { type: "start" },
        { type: "text-start", id: "t1" },
        { type: "text-delta", id: "t1", delta: "FX Hub " },
        { type: "text-delta", id: "t1", delta: "book" },
        { type: "text-end", id: "t1" },
        { type: "finish" },
      ]),
    );
    const out = await forwardFinancialTurn(loaded!.config, loaded!.machineKey, loaded!.session, "levels?", fetchFn);
    expect(out).toEqual({ reply: "FX Hub book" });
    expect(fetchFn).toHaveBeenCalledOnce();
    const [url, init] = fetchFn.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe("https://chat.digithings.ai/api/chat");
    const headers = init.headers as Record<string, string>;
    expect(headers.authorization).toBe(`Bearer ${KEY}`);
    expect(headers["x-digi-model"]).toBe(TENANT.cheapModel);
    expect(init.signal).toBeInstanceOf(AbortSignal);
    const raw = String(init.body);
    expect(raw).not.toContain(KEY);
    // The shape the route's UIMessage reader takes: id, role and a text part list.
    const body = JSON.parse(raw) as { messages: { id: string; role: string; parts: { type: string; text: string }[] }[] };
    expect(Object.keys(body)).toEqual(["messages"]);
    expect(body.messages).toHaveLength(1);
    const [message] = body.messages;
    expect(typeof message!.id).toBe("string");
    expect(message!.role).toBe("user");
    expect(message!.parts).toHaveLength(1);
    expect(message!.parts[0]!.type).toBe("text");
    expect(message!.parts[0]!.text).toContain("FX Hub");
    expect(message!.parts[0]!.text).toContain("/fx/pairs");
    expect(message!.parts[0]!.text.endsWith("levels?")).toBe(true);
  });

  it("reads no reply from an error chunk, an empty stream, or a refused turn", async () => {
    expect(readStreamReply("data: {\"type\":\"error\",\"errorText\":\"boom\"}\n\n")).toBeNull();
    expect(readStreamReply("data: [DONE]\n\n")).toBeNull();
    expect(readStreamReply("not a stream")).toBeNull();
    const loaded = await loadFinancialSession(env(TENANT), "baseline");
    const refused = vi.fn(async () => Response.json({ error: "unauthorized" }, { status: 401 }));
    expect(await forwardFinancialTurn(loaded!.config, loaded!.machineKey, loaded!.session, "hi", refused)).toEqual({
      error: "digichat returned no reply",
    });
    const down = vi.fn(async () => {
      throw new TypeError("network");
    });
    expect(await forwardFinancialTurn(loaded!.config, loaded!.machineKey, loaded!.session, "hi", down)).toEqual({
      error: "digichat could not be reached",
    });
  });
});
