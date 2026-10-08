import { afterEach, describe, expect, it, vi } from "vitest";
import app, { type Env } from "../index";

const ENV: Env = { DASHBOARD_TRUST_IDENTITY_HEADERS: "1", DASHBOARD_DEV_CALLER: "enterprise+12x" };
const BRIEF: Env = { DASHBOARD_TRUST_IDENTITY_HEADERS: "1", DASHBOARD_DEV_CALLER: "brief" };
const FREE: Env = { DASHBOARD_TRUST_IDENTITY_HEADERS: "1",};
const CORE: Env = { DASHBOARD_TRUST_IDENTITY_HEADERS: "1",
  ...ENV,
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "core-key",
};

const user = { "x-digi-user": "ada@desk" };

afterEach(() => vi.unstubAllGlobals());

describe("phase 4 shell, settings, chat", () => {
  it("desks and features come from the catalog and do not mark a desk active", async () => {
    const desks = await app.fetch(new Request("https://x/desks?retrieval_pin=pin-1"), ENV);
    const body = (await desks.json()) as {
      retrieval_pin: string;
      data: { desks: { id: string; active: null; chip: string | null }[]; hint: string };
      provenance: { source: string };
    };
    expect(desks.status).toBe(200);
    expect(body.retrieval_pin).toBe("pin-1");
    expect(body.provenance.source).toBe("access_policy");
    expect(body.data.desks.map((d) => d.id)).toEqual(["baseline", "fx"]);
    expect(body.data.desks.every((d) => d.active === null)).toBe(true);
    expect(body.data.desks.find((d) => d.id === "fx")?.chip).toBe("12x");
    const features = await app.fetch(new Request("https://x/features"), ENV);
    const flags = ((await features.json()) as { data: { flags: { key: string; tag: string }[] } }).data.flags;
    expect(flags.some((f) => f.key === "/tools/terminal" && f.tag === "soon")).toBe(true);
    expect(flags.some((f) => f.key === "/tools/chat" && f.tag === "wip")).toBe(true);
    const spine = await app.fetch(new Request("https://x/desks/active/spine"), ENV);
    const items = ((await spine.json()) as { data: { desk_id: string; items: { href: string }[] } }).data;
    expect(items.desk_id).toBe("baseline");
    expect(items.items.some((i) => i.href === "/brief")).toBe(true);
  });

  it("omits the fx desk from callers outside the 12x group", async () => {
    const desks = await app.fetch(new Request("https://x/desks"), BRIEF);
    const body = (await desks.json()) as { data: { desks: { id: string; name: string; chip: string | null }[] } };
    expect(desks.status).toBe(200);
    expect(body.data.desks.map((d) => d.id)).toEqual(["baseline"]);
    expect(JSON.stringify(body)).not.toMatch(/fx hub|12x/i);
    const features = await app.fetch(new Request("https://x/features"), BRIEF);
    const flags = ((await features.json()) as { data: { flags: { key: string; text: string }[] } }).data.flags;
    expect(flags.some((f) => f.key === "/fx" || /fx hub|12x/i.test(f.text))).toBe(false);
    expect(flags.some((f) => f.key === "/tools/terminal")).toBe(true);
  });

  it("settings reads are empty and writes are not provisioned", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const prefs = await app.fetch(new Request("https://x/settings/prefs"), ENV);
    const prefsBody = (await prefs.json()) as { data: { display_name: null; daily_digest: null; note: string } };
    expect(prefs.status).toBe(200);
    expect(prefsBody.data.display_name).toBeNull();
    expect(prefsBody.data.daily_digest).toBeNull();
    expect(prefsBody.data.note).toContain("not configured");
    const put = await app.fetch(new Request("https://x/settings/prefs", { method: "PUT", headers: user, body: "{}" }), ENV);
    expect(put.status).toBe(503);
    expect(((await put.json()) as { error: { code: string } }).error.code).toBe("not_provisioned");
    const anon = await app.fetch(new Request("https://x/settings/prefs", { method: "PUT", body: "{}" }), ENV);
    expect(anon.status).toBe(401);
    const feed = await app.fetch(new Request("https://x/settings/fx-feed"), ENV);
    const feedBody = (await feed.json()) as { data: { keys: unknown[]; feed: null; generation: { note: string } } };
    expect(feedBody.data.keys).toEqual([]);
    expect(feedBody.data.feed).toBeNull();
    expect(feedBody.data.generation.note).toContain("not configured");
    const connect = await app.fetch(new Request("https://x/settings/brokers/connect", { method: "POST", headers: user, body: "{}" }), BRIEF);
    expect(connect.status).toBe(503);
    const mint = await app.fetch(new Request("https://x/settings/keys", { method: "POST", headers: user, body: "{}" }), ENV);
    expect(mint.status).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("chat fails closed without a digichat database", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect((await app.fetch(new Request("https://x/chat/sessions"), FREE)).status).toBe(403);
    const sessions = await app.fetch(new Request("https://x/chat/sessions"), BRIEF);
    expect(sessions.status).toBe(502);
    expect(((await sessions.json()) as { error: { message: string } }).error.message).toContain("digichat is not configured");
    const created = await app.fetch(new Request("https://x/chat/sessions", { method: "POST", headers: user, body: "{}" }), BRIEF);
    expect(created.status).toBe(503);
    const renamed = await app.fetch(new Request("https://x/chat/sessions/s1", { method: "PUT", headers: user, body: "{}" }), BRIEF);
    expect(renamed.status).toBe(503);
    const sent = await app.fetch(new Request("https://x/chat/sessions/s1/messages", { method: "POST", headers: user, body: "{}" }), BRIEF);
    expect(sent.status).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("latest run reads run_health and leaves a missing duration null", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json([{ run_date: "2026-09-03", status: "ok", finished_at: null, duration_s: null }])));
    const res = await app.fetch(new Request("https://x/pipeline/runs/latest"), CORE);
    const body = (await res.json()) as { data: { run_date: string; status: string; duration_s: null }; provenance: { source: string } };
    expect(res.status).toBe(200);
    expect(body.data).toMatchObject({ run_date: "2026-09-03", status: "ok", duration_s: null });
    expect(body.provenance.source).toBe("core:run_health");
  });
});
