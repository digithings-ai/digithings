/**
 * Narrow Supabase Auth + PostgREST client for the two FX Hub functions.
 *
 * `@supabase/supabase-js` is not a dependency of this worker. The calls these
 * functions actually make are four HTTP requests, so this file is those four
 * requests and nothing else. Every request goes through `apiKeyOnlyFetch`,
 * which keeps a new-format key on `apikey` and off `Authorization`.
 *
 * The response shapes match what supabase-js hands back to the edge handlers:
 * GoTrue's flat `generate_link` body is read as `properties`, and `verify`
 * is read as `session`.
 */

import { apiKeyOnlyFetch } from "./http";

export interface GrantLookup {
  data: { email: string } | null;
  error: { message: string } | null;
}

export interface MagicLinkResult {
  data: {
    properties: {
      hashed_token?: string;
      verification_type?: string;
    } | null;
  };
  error: { message: string } | null;
}

export interface VerifyResult {
  data: {
    session: {
      access_token: string;
      refresh_token: string;
      expires_in: number;
    } | null;
  };
  error: { message: string } | null;
}

export interface UpsertResult {
  error: { message: string } | null;
}

function baseUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

function messageOf(data: unknown): string {
  if (typeof data === "string") return data;
  if (data && typeof data === "object") {
    const rec = data as Record<string, unknown>;
    if (typeof rec.message === "string") return rec.message;
    if (typeof rec.msg === "string") return rec.msg;
    if (typeof rec.error_description === "string") return rec.error_description;
  }
  return "";
}

async function readJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (text.length === 0) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function call(
  apiKey: string,
  url: string,
  init: { method: string; body?: unknown; headers?: Record<string, string> },
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("apikey", apiKey);
  headers.set("Authorization", `Bearer ${apiKey}`);
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  return apiKeyOnlyFetch(url, {
    method: init.method,
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
}

/** `from("fx_hub_grants").select("email").eq("email", email).maybeSingle()`. */
export async function lookupGrant(
  url: string,
  secretKey: string,
  email: string,
): Promise<GrantLookup> {
  const endpoint = new URL(`${baseUrl(url)}/rest/v1/fx_hub_grants`);
  endpoint.searchParams.set("select", "email");
  endpoint.searchParams.set("email", `eq.${email}`);
  const res = await call(secretKey, endpoint.toString(), {
    method: "GET",
    headers: { Accept: "application/vnd.pgrst.object+json" },
  });
  const data = await readJson(res);
  if (res.status === 406) return { data: null, error: null };
  if (!res.ok) return { data: null, error: { message: messageOf(data) } };
  if (data && typeof data === "object" && !Array.isArray(data)) {
    const emailValue = (data as { email?: unknown }).email;
    if (typeof emailValue === "string" && emailValue.length > 0) {
      return { data: { email: emailValue }, error: null };
    }
  }
  return { data: null, error: null };
}

/** `auth.admin.generateLink({ type: "magiclink", email })`. */
export async function generateMagicLink(
  url: string,
  secretKey: string,
  email: string,
): Promise<MagicLinkResult> {
  const res = await call(secretKey, `${baseUrl(url)}/auth/v1/admin/generate_link`, {
    method: "POST",
    body: { type: "magiclink", email },
  });
  const data = await readJson(res);
  if (!res.ok || data === null || typeof data !== "object" || Array.isArray(data)) {
    return { data: { properties: null }, error: { message: messageOf(data) } };
  }
  const rec = data as Record<string, unknown>;
  const source =
    rec.properties && typeof rec.properties === "object" && !Array.isArray(rec.properties)
      ? (rec.properties as Record<string, unknown>)
      : rec;
  const hashed = source.hashed_token;
  const verificationType = source.verification_type;
  return {
    data: {
      properties: {
        ...(typeof hashed === "string" && hashed.length > 0 ? { hashed_token: hashed } : {}),
        ...(typeof verificationType === "string" ? { verification_type: verificationType } : {}),
      },
    },
    error: null,
  };
}

/** `auth.verifyOtp({ type, token_hash })` with the publishable key. */
export async function verifyOtp(
  url: string,
  publishableKey: string,
  args: { type: string; tokenHash: string },
): Promise<VerifyResult> {
  const res = await call(publishableKey, `${baseUrl(url)}/auth/v1/verify`, {
    method: "POST",
    body: { type: args.type, token_hash: args.tokenHash },
  });
  const data = await readJson(res);
  if (!res.ok || data === null || typeof data !== "object" || Array.isArray(data)) {
    return { data: { session: null }, error: { message: messageOf(data) } };
  }
  const rec = data as Record<string, unknown>;
  const sessionSource =
    rec.session && typeof rec.session === "object" && !Array.isArray(rec.session)
      ? (rec.session as Record<string, unknown>)
      : rec;
  const accessToken = sessionSource.access_token;
  const refreshToken = sessionSource.refresh_token;
  const expiresIn = sessionSource.expires_in;
  if (typeof accessToken !== "string" || accessToken.length === 0) {
    return { data: { session: null }, error: null };
  }
  return {
    data: {
      session: {
        access_token: accessToken,
        refresh_token: typeof refreshToken === "string" ? refreshToken : "",
        expires_in: typeof expiresIn === "number" ? expiresIn : 0,
      },
    },
    error: null,
  };
}

/** `from("fx_hub_grants").upsert({ email, note }, { onConflict: "email" })`. */
export async function upsertGrant(
  url: string,
  secretKey: string,
  row: { email: string; note: string },
): Promise<UpsertResult> {
  const endpoint = new URL(`${baseUrl(url)}/rest/v1/fx_hub_grants`);
  endpoint.searchParams.set("on_conflict", "email");
  const res = await call(secretKey, endpoint.toString(), {
    method: "POST",
    headers: { Prefer: "resolution=merge-duplicates,return=minimal" },
    body: row,
  });
  if (res.ok) return { error: null };
  const data = await readJson(res);
  return { error: { message: messageOf(data) } };
}
