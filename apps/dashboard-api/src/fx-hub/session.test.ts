import { afterEach, describe, expect, it, vi } from "vitest";
import type { FxHubEnv } from "./env";
import { createFxHubFetch } from "./router";
import { handleFxHubSession } from "./session";

// Contract parity for the Workers port of fx-hub-session.
//
// The nine behaviours in the edge-function suite are split across this file
// and grant-sync.test.ts. The fake Supabase is a fetch mock: the same paths
// the edge tests served (`/rest/v1/fx_hub_grants`, `/auth/v1/admin/generate_link`,
// `/auth/v1/verify`) and the same header observations (apikey set, new-format
// key never on Authorization).

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
  return new Request("https://function.test/fx-hub-session", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Sync-Secret": secret,
    },
    body: JSON.stringify(body),
  });
}

function installFake(opts: {
  granted?: boolean;
  linkBody?: Record<string, unknown>;
  verifyStatus?: number;
  verifyBody?: Record<string, unknown>;
} = {}): Seen[] {
  const granted = opts.granted ?? true;
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
    });

    if (url.pathname === "/rest/v1/fx_hub_grants") {
      return Response.json(granted ? { email: GRANTED_EMAIL } : null);
    }
    if (url.pathname === "/auth/v1/admin/generate_link") {
      return Response.json(
        opts.linkBody ?? {
          action_link: "https://example.test/confirm",
          email_otp: "123456",
          hashed_token: "fake-hashed-token",
          redirect_to: "https://example.test",
          verification_type: "magiclink",
          id: "user-id",
          email: GRANTED_EMAIL,
        },
      );
    }
    if (url.pathname === "/auth/v1/verify") {
      return Response.json(
        opts.verifyBody ?? {
          access_token: "fake-access-token",
          refresh_token: "fake-refresh-token",
          token_type: "bearer",
          expires_in: 3600,
          user: { id: "user-id", email: GRANTED_EMAIL },
        },
        { status: opts.verifyStatus ?? 200 },
      );
    }
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return seen;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fx-hub-session", () => {
  it("mints a session using only the new keys", async () => {
    const seen = installFake({ granted: true });
    const res = await handleFxHubSession(post({ email: GRANTED_EMAIL }), newKeyEnv());
    const body = (await res.json()) as Record<string, unknown>;

    expect(res.status).toBe(200);
    expect(body).toEqual({
      ok: true,
      access_token: "fake-access-token",
      refresh_token: "fake-refresh-token",
      expires_in: 3600,
    });

    const grantLookup = seen.find((row) => row.path === "/rest/v1/fx_hub_grants");
    const generateLink = seen.find((row) => row.path === "/auth/v1/admin/generate_link");
    const verify = seen.find((row) => row.path === "/auth/v1/verify");
    expect(grantLookup?.method).toBe("GET");
    expect(decodeURIComponent(grantLookup?.search ?? "")).toContain(`email=eq.${GRANTED_EMAIL}`);
    expect(grantLookup?.apikey).toBe(SECRET_KEY);
    expect(generateLink?.apikey).toBe(SECRET_KEY);
    expect(verify?.apikey).toBe(PUBLISHABLE_KEY);
    expect(JSON.parse(verify?.body ?? "{}")).toEqual({
      type: "magiclink",
      token_hash: "fake-hashed-token",
    });
  });

  it("sends the new key on apikey and never as Bearer", async () => {
    const seen = installFake({ granted: true });
    await handleFxHubSession(post({ email: GRANTED_EMAIL }), newKeyEnv());

    expect(seen.length).toBeGreaterThanOrEqual(3);
    for (const call of seen) {
      const auth = call.authorization ?? "";
      expect(auth, `${call.path} leaked the secret key on Authorization`).not.toContain(SECRET_KEY);
      expect(auth, `${call.path} leaked the publishable key on Authorization`).not.toContain(
        PUBLISHABLE_KEY,
      );
      expect(call.apikey === SECRET_KEY || call.apikey === PUBLISHABLE_KEY).toBe(true);
    }
  });

  it("forwards the verification_type generateLink reports", async () => {
    const seen = installFake({
      granted: true,
      linkBody: {
        hashed_token: "signup-token",
        verification_type: "signup",
      },
    });
    const res = await handleFxHubSession(post({ email: GRANTED_EMAIL }), newKeyEnv());
    expect(res.status).toBe(200);
    const verify = seen.find((row) => row.path === "/auth/v1/verify");
    expect(JSON.parse(verify?.body ?? "{}")).toEqual({
      type: "signup",
      token_hash: "signup-token",
    });
  });

  it("refuses to fall back to the legacy keys", async () => {
    const seen = installFake({ granted: true });
    const res = await handleFxHubSession(post({ email: GRANTED_EMAIL }), {
      FX_HUB_GRANT_SYNC_SECRET: SYNC_SECRET,
      SUPABASE_ANON_KEY: "legacy-anon-jwt",
      SUPABASE_SERVICE_ROLE_KEY: "legacy-service-role-jwt",
    });
    const body = (await res.json()) as { ok: boolean; code: string; message: string };

    expect(res.status).toBe(500);
    expect(body.ok).toBe(false);
    expect(body.code).toBe("API_KEYS_UNCONFIGURED");
    expect(body.message).toBe(
      "project API keys not configured: SUPABASE_URL, SUPABASE_SECRET_KEYS[default], SUPABASE_PUBLISHABLE_KEYS[default]",
    );
    expect(body.message).not.toContain("legacy-anon-jwt");
    expect(body.message).not.toContain("legacy-service-role-jwt");
    expect(seen).toHaveLength(0);
  });

  it("reports unparseable and empty key dictionaries", async () => {
    for (const raw of ["", "not-json", "{}", JSON.stringify({ default: "" })]) {
      const seen = installFake({ granted: true });
      const res = await handleFxHubSession(post({ email: GRANTED_EMAIL }), {
        FX_HUB_GRANT_SYNC_SECRET: SYNC_SECRET,
        SUPABASE_URL,
        SUPABASE_SECRET_KEYS: raw,
        SUPABASE_PUBLISHABLE_KEYS: raw,
      });
      const body = (await res.json()) as { code: string; message: string };
      expect(res.status, `raw=${JSON.stringify(raw)}`).toBe(500);
      expect(body.code, `raw=${JSON.stringify(raw)}`).toBe("API_KEYS_UNCONFIGURED");
      expect(body.message).toBe(
        "project API keys not configured: SUPABASE_SECRET_KEYS[default], SUPABASE_PUBLISHABLE_KEYS[default]",
      );
      if (raw.length > 0) expect(body.message).not.toContain(raw);
      expect(seen).toHaveLength(0);
      vi.unstubAllGlobals();
    }
  });

  it("does not treat a non-default dictionary entry as the key", async () => {
    const seen = installFake({ granted: true });
    const res = await handleFxHubSession(post({ email: GRANTED_EMAIL }), {
      FX_HUB_GRANT_SYNC_SECRET: SYNC_SECRET,
      SUPABASE_URL,
      SUPABASE_SECRET_KEYS: JSON.stringify({ other: SECRET_KEY }),
      SUPABASE_PUBLISHABLE_KEYS: JSON.stringify({ other: PUBLISHABLE_KEY }),
    });
    const body = (await res.json()) as { code: string; message: string };
    expect(res.status).toBe(500);
    expect(body.code).toBe("API_KEYS_UNCONFIGURED");
    expect(body.message).not.toContain(SECRET_KEY);
    expect(body.message).not.toContain(PUBLISHABLE_KEY);
    expect(seen).toHaveLength(0);
  });

  it("denies an email that is not granted and does not verify", async () => {
    const seen = installFake({ granted: false });
    const res = await handleFxHubSession(post({ email: GRANTED_EMAIL }), newKeyEnv());
    const body = (await res.json()) as { code: string };

    expect(res.status).toBe(403);
    expect(body.code).toBe("NOT_GRANTED");
    expect(seen.some((row) => row.path === "/auth/v1/verify")).toBe(false);
    expect(seen.some((row) => row.path === "/auth/v1/admin/generate_link")).toBe(false);
    expect(seen.some((row) => row.path === "/rest/v1/fx_hub_grants")).toBe(true);
  });

  it("returns LINK_FAILED when generateLink has no hashed token", async () => {
    const seen = installFake({ granted: true, linkBody: { verification_type: "magiclink" } });
    const res = await handleFxHubSession(post({ email: GRANTED_EMAIL }), newKeyEnv());
    const body = (await res.json()) as { code: string };
    expect(res.status).toBe(500);
    expect(body.code).toBe("LINK_FAILED");
    expect(seen.some((row) => row.path === "/auth/v1/verify")).toBe(false);
  });

  it("returns VERIFY_FAILED when verifyOtp returns no session", async () => {
    installFake({
      granted: true,
      verifyStatus: 400,
      verifyBody: { message: "Email link is invalid or has expired" },
    });
    const res = await handleFxHubSession(post({ email: GRANTED_EMAIL }), newKeyEnv());
    const body = (await res.json()) as { code: string; message: string };
    expect(res.status).toBe(500);
    expect(body.code).toBe("VERIFY_FAILED");
    expect(body.message).toBe("Email link is invalid or has expired");
  });

  it("keeps the shared-secret boundary intact", async () => {
    const seen = installFake({ granted: true });
    const env = newKeyEnv();

    expect((await handleFxHubSession(post({ email: GRANTED_EMAIL }, "wrong"), env)).status).toBe(401);
    expect(
      (
        await handleFxHubSession(
          new Request("https://function.test/fx-hub-session", { method: "GET" }),
          env,
        )
      ).status,
    ).toBe(405);
    expect((await handleFxHubSession(post({ email: "not-an-email" }), env)).status).toBe(400);

    const malformed = new Request("https://function.test/fx-hub-session", {
      method: "POST",
      headers: { "X-Sync-Secret": "wrong", "Content-Type": "application/json" },
      body: "{",
    });
    expect((await handleFxHubSession(malformed, env)).status).toBe(401);
    expect(seen).toHaveLength(0);
  });

  it("answers 400 BAD_JSON for a malformed body after auth", async () => {
    const seen = installFake({ granted: true });
    const res = await handleFxHubSession(
      new Request("https://function.test/fx-hub-session", {
        method: "POST",
        headers: { "X-Sync-Secret": SYNC_SECRET, "Content-Type": "application/json" },
        body: "{",
      }),
      newKeyEnv(),
    );
    const body = (await res.json()) as { code: string };
    expect(res.status).toBe(400);
    expect(body.code).toBe("BAD_JSON");
    expect(seen).toHaveLength(0);
  });

  it("routes POST /fx-hub-session through the worker fetch handler", async () => {
    installFake({ granted: true });
    const handler = createFxHubFetch(newKeyEnv());
    const res = await handler.fetch(post({ email: GRANTED_EMAIL }));
    expect(res.status).toBe(200);
  });
});
