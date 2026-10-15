import { afterEach, describe, expect, it, vi } from "vitest";
import type { FxHubEnv } from "./env";
import { handleFxHubGrantSync } from "./grant-sync";
import { createFxHubFetch } from "./router";

// Contract parity for the Workers port of fx-hub-grant-sync.
// Same shared-secret boundary and new-key rules as fx-hub-session; this
// function reads only SUPABASE_URL and SUPABASE_SECRET_KEYS[default].

const SYNC_SECRET = "test-sync-secret";
const SECRET_KEY = "sb_secret_fakevalue";
const PUBLISHABLE_KEY = "sb_publishable_fakevalue";
const GRANTED_EMAIL = "granted@example.test";
const SUPABASE_URL = "http://127.0.0.1:9";

type Seen = {
  path: string;
  apikey: string | null;
  authorization: string | null;
  method: string;
  search: string;
  body: string | null;
  prefer: string | null;
};

function newKeyEnv(extra: FxHubEnv = {}): FxHubEnv {
  return {
    FX_HUB_GRANT_SYNC_SECRET: SYNC_SECRET,
    SUPABASE_URL,
    SUPABASE_SECRET_KEYS: JSON.stringify({ default: SECRET_KEY }),
    SUPABASE_PUBLISHABLE_KEYS: JSON.stringify({ default: PUBLISHABLE_KEY }),
    ...extra,
  };
}

function post(body: unknown, secret = SYNC_SECRET): Request {
  return new Request("https://function.test/fx-hub-grant-sync", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Sync-Secret": secret,
    },
    body: JSON.stringify(body),
  });
}

function installFake(opts: { status?: number; errorMessage?: string } = {}): Seen[] {
  const seen: Seen[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = input instanceof Request ? input : new Request(input, init);
    const url = new URL(req.url);
    const body = req.method === "GET" || req.method === "HEAD" ? null : await req.text();
    seen.push({
      path: url.pathname,
      apikey: req.headers.get("apikey"),
      authorization: req.headers.get("authorization"),
      method: req.method,
      search: url.search,
      body,
      prefer: req.headers.get("prefer"),
    });
    if (opts.status && opts.status >= 400) {
      return Response.json({ message: opts.errorMessage ?? "upsert failed", code: "23505" }, {
        status: opts.status,
      });
    }
    return new Response(null, { status: 201 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return seen;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fx-hub-grant-sync", () => {
  it("upserts with the new secret key only", async () => {
    const seen = installFake();
    const res = await handleFxHubGrantSync(post({ email: GRANTED_EMAIL }), newKeyEnv());
    const body = (await res.json()) as { ok: boolean };

    expect(res.status).toBe(200);
    expect(body).toEqual({ ok: true });

    const upsert = seen.find((row) => row.path === "/rest/v1/fx_hub_grants");
    expect(upsert?.apikey).toBe(SECRET_KEY);
    expect(upsert?.authorization ?? "").not.toContain(SECRET_KEY);
    expect(upsert?.method).toBe("POST");
    expect(upsert?.search).toContain("on_conflict=email");
    expect(upsert?.prefer ?? "").toContain("resolution=merge-duplicates");
    expect(JSON.parse(upsert?.body ?? "{}")).toEqual({
      email: GRANTED_EMAIL,
      note: "synced from core client_product_grants",
    });
    expect(seen.some((row) => row.apikey === PUBLISHABLE_KEY)).toBe(false);
  });

  it("refuses to fall back to the legacy keys", async () => {
    const seen = installFake();
    const res = await handleFxHubGrantSync(post({ email: GRANTED_EMAIL }), {
      FX_HUB_GRANT_SYNC_SECRET: SYNC_SECRET,
      SUPABASE_URL,
      SUPABASE_SERVICE_ROLE_KEY: "legacy-service-role-jwt",
    });
    const body = (await res.json()) as { code: string; message: string };

    expect(res.status).toBe(500);
    expect(body.code).toBe("API_KEYS_UNCONFIGURED");
    expect(body.message).toContain("SUPABASE_SECRET_KEYS[default]");
    expect(body.message).toBe(
      "project API keys not configured: SUPABASE_SECRET_KEYS[default]",
    );
    expect(body.message).not.toContain("legacy-service-role-jwt");
    expect(seen).toHaveLength(0);
  });

  it("returns DB_ERROR when the upsert fails", async () => {
    installFake({ status: 409, errorMessage: "upsert failed" });
    const res = await handleFxHubGrantSync(post({ email: GRANTED_EMAIL }), newKeyEnv());
    const body = (await res.json()) as { ok: boolean; code: string; message: string };
    expect(res.status).toBe(500);
    expect(body.ok).toBe(false);
    expect(body.code).toBe("DB_ERROR");
    expect(body.message).toBe("upsert failed");
  });

  it("keeps the shared-secret boundary intact", async () => {
    const seen = installFake();
    const env = newKeyEnv();

    expect((await handleFxHubGrantSync(post({ email: GRANTED_EMAIL }, "wrong"), env)).status).toBe(
      401,
    );
    expect(
      (
        await handleFxHubGrantSync(
          new Request("https://function.test/fx-hub-grant-sync", { method: "GET" }),
          env,
        )
      ).status,
    ).toBe(405);
    expect((await handleFxHubGrantSync(post({ email: "not-an-email" }), env)).status).toBe(400);
    expect(seen).toHaveLength(0);
  });

  it("normalizes the email before the upsert", async () => {
    const seen = installFake();
    const res = await handleFxHubGrantSync(post({ email: "  Granted@Example.Test " }), newKeyEnv());
    expect(res.status).toBe(200);
    expect(JSON.parse(seen[0]?.body ?? "{}")).toEqual({
      email: GRANTED_EMAIL,
      note: "synced from core client_product_grants",
    });
  });

  it("routes POST /fx-hub-grant-sync through the worker fetch handler", async () => {
    installFake();
    const handler = createFxHubFetch(newKeyEnv());
    const res = await handler.fetch(post({ email: GRANTED_EMAIL }));
    expect(res.status).toBe(200);
  });
});
