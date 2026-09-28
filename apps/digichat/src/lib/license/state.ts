/**
 * digichat customer-license state: startup verification + revoke latch.
 *
 * Implements the container half of
 * `docs/superpowers/specs/2026-09-28-digichat-license-heartbeat-impl.md`
 * §3 (startup verification, local only, fail-open) and §4 (revoke latch
 * state machine). The heartbeat sender lives in `./heartbeat`; the shared
 * version helper in `./version`.
 *
 * States: `unlicensed` (no credential or local verify failure — serves),
 * `valid` (serves), `expired` (refuses, `503 license_expired`), `revoked`
 * (refuses, `503 license_revoked`). Only `revoked`/`expired` refuse product
 * traffic; everything else serves (fail-open, bounded by `exp`).
 *
 * The record lives on `globalThis`, not in a module-level `let`: the
 * instrumentation module and the route handlers are separate compiled
 * bundles in the standalone build, and Next does not promise they share
 * module instances. A bare `let` could give each bundle its own copy and
 * make the latch invisible to the routes it must guard.
 *
 * Secret hygiene: the raw license JWT and any PEM material are never logged,
 * never returned in a response, and never written to a file. `license_id`,
 * the customer slug, and `exp` are safe to log.
 */

import { createPublicKey, createVerify } from "node:crypto";
import { readFileSync } from "node:fs";
import { getDigichatConfig } from "@/lib/deploy-config/loader";
import {
  getEmbedTenantRegistry,
  normalizeEmbedHost,
} from "@/lib/embed-tenants";

export type LicenseState = "unlicensed" | "valid" | "expired" | "revoked";

export interface LicenseSnapshot {
  state: LicenseState;
  /** Closed reason enum (never a secret): e.g. `missing_credential`, `ok`, `expired`. */
  detail?: string;
  licenseId?: string;
  /** Customer slug (`sub` claim, `tenant_slug` fallback). */
  sub?: string;
  /** Seconds-since-epoch `exp` claim. */
  exp?: number;
}

interface LicenseRecord extends LicenseSnapshot {
  /** Raw compact JWT. In-memory only; never logged or returned. */
  rawJwt: string | null;
  /** Normalized configured hosts (§3.5 advisory comparison input). */
  hostsConfigured: string[];
  /** ISO-8601 UTC of process start. */
  startedAt: string;
}

export const LICENSE_CLOCK_SKEW_LEEWAY_SEC = 300;
export const LICENSE_AUDIENCE = "digichat-license";
export const LICENSE_KIND = "digichat-license";
export const LICENSE_DEFAULT_ISSUER = "http://127.0.0.1:8005";

const GLOBAL_KEY = "__digichatLicenseState";

function freshRecord(): LicenseRecord {
  return {
    state: "unlicensed",
    detail: "missing_credential",
    rawJwt: null,
    hostsConfigured: [],
    startedAt: new Date().toISOString(),
  };
}

function store(): { record: LicenseRecord } {
  const g = globalThis as unknown as Record<
    string,
    { record: LicenseRecord } | undefined
  >;
  if (!g[GLOBAL_KEY]) g[GLOBAL_KEY] = { record: freshRecord() };
  return g[GLOBAL_KEY] as { record: LicenseRecord };
}

/** Test hook — clears the `globalThis` record so stubbed envs take effect. */
export function resetLicenseStateForTests(): void {
  const g = globalThis as unknown as Record<string, unknown>;
  delete g[GLOBAL_KEY];
}

/**
 * Raw credential: `DIGICHAT_LICENSE_FILE` wins when set and readable, else
 * `DIGICHAT_LICENSE_JWT`. An unreadable file falls back to the inline env.
 */
export function readLicenseJwt(
  env: NodeJS.ProcessEnv = process.env,
): string | null {
  const file = env.DIGICHAT_LICENSE_FILE?.trim();
  if (file) {
    try {
      const contents = readFileSync(file, "utf8").trim();
      if (contents) return contents;
    } catch {
      // Unreadable file falls back to the inline env below.
    }
  }
  const inline = env.DIGICHAT_LICENSE_JWT?.trim();
  return inline || null;
}

/** Split one-or-more concatenated SPKI PEMs on BEGIN boundaries; trim, drop empties. */
export function splitPublicKeys(pemBundle: string | undefined): string[] {
  if (!pemBundle?.trim()) return [];
  return pemBundle
    .split("-----BEGIN PUBLIC KEY-----")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => `-----BEGIN PUBLIC KEY-----\n${s}`);
}

function base64urlDecode(segment: string): Buffer {
  if (!segment || !/^[A-Za-z0-9_-]+$/.test(segment)) throw new Error("malformed_jwt");
  const padded = segment + "=".repeat((4 - (segment.length % 4)) % 4);
  return Buffer.from(padded, "base64");
}

export interface VerifySuccess {
  ok: true;
  licenseId: string;
  sub: string;
  exp: number;
  hosts: string[];
}

export interface VerifyFailure {
  ok: false;
  detail: string;
}

function fail(detail: string): VerifyFailure {
  return { ok: false, detail };
}

/**
 * Pure local verification (§3.1 order: parse → signature → claims). No I/O
 * other than the caller's env/file read; no network. `nowSec` is injectable
 * for clock-skew tests.
 */
export function verifyLicenseJwt(
  token: string,
  opts: {
    publicKeyPem?: string;
    expectedIssuer?: string;
    nowSec?: number;
  } = {},
): VerifySuccess | VerifyFailure {
  const nowSec = opts.nowSec ?? Math.floor(Date.now() / 1000);

  // 1. Parse.
  const segments = token.split(".");
  if (segments.length !== 3) return fail("malformed_jwt");
  let header: unknown;
  let payload: unknown;
  try {
    header = JSON.parse(base64urlDecode(segments[0]).toString("utf8"));
    payload = JSON.parse(base64urlDecode(segments[1]).toString("utf8"));
  } catch {
    // Distinguish undecodable segments from decodable-but-not-JSON payloads.
    try {
      base64urlDecode(segments[0]);
      base64urlDecode(segments[1]);
    } catch {
      return fail("malformed_jwt");
    }
    return fail("bad_json");
  }
  if (
    typeof header !== "object" ||
    header === null ||
    typeof payload !== "object" ||
    payload === null
  ) {
    return fail("bad_json");
  }
  const h = header as Record<string, unknown>;
  const p = payload as Record<string, unknown>;

  // 2. Signature. Only RS256 is accepted — `none` and every symmetric alg
  // are rejected outright (classic key-confusion hole).
  if (h.alg !== "RS256") return fail("bad_signature");
  const candidates = splitPublicKeys(opts.publicKeyPem);
  if (candidates.length === 0) return fail("no_public_key");
  let signature: Buffer;
  try {
    signature = base64urlDecode(segments[2]);
  } catch {
    return fail("malformed_jwt");
  }
  const signingInput = Buffer.from(`${segments[0]}.${segments[1]}`, "utf8");
  const verified = candidates.some((pem) => {
    try {
      const key = createPublicKey(pem);
      return createVerify("RSA-SHA256").update(signingInput).verify(key, signature);
    } catch {
      return false;
    }
  });
  if (!verified) return fail("bad_signature");

  // 3. Claims, in order: exp/iat, aud, iss, kind, hosts, sub/license_id.
  if (typeof p.exp !== "number" || !Number.isFinite(p.exp)) return fail("exp_missing");
  if (nowSec > p.exp + LICENSE_CLOCK_SKEW_LEEWAY_SEC) return fail("expired");
  if (
    typeof p.iat === "number" &&
    Number.isFinite(p.iat) &&
    p.iat > nowSec + LICENSE_CLOCK_SKEW_LEEWAY_SEC
  ) {
    return fail("claims_missing");
  }
  if (p.aud !== LICENSE_AUDIENCE) return fail("aud_mismatch");
  const expectedIssuer = (opts.expectedIssuer ?? LICENSE_DEFAULT_ISSUER).trim();
  const iss = typeof p.iss === "string" ? p.iss.trim() : "";
  if (iss !== expectedIssuer) return fail("iss_mismatch");
  if (p.kind !== LICENSE_KIND) return fail("kind_mismatch");
  if (
    !Array.isArray(p.hosts) ||
    p.hosts.length === 0 ||
    p.hosts.some((x) => typeof x !== "string" || !x)
  ) {
    return fail("hosts_invalid");
  }
  const sub =
    typeof p.sub === "string" && p.sub
      ? p.sub
      : typeof p.tenant_slug === "string"
        ? p.tenant_slug
        : "";
  const licenseId =
    typeof p.license_id === "string" && p.license_id
      ? p.license_id
      : typeof p.jti === "string" && p.jti
        ? p.jti
        : "";
  if (!sub || !licenseId) return fail("claims_missing");

  return { ok: true, licenseId, sub, exp: p.exp, hosts: p.hosts as string[] };
}

/**
 * Advisory hosts comparison (§3.5): the license `hosts` claim against the
 * canonical configured hosts — merged deploy-config `hosts` keys plus the
 * `DIGICHAT_EMBED_TENANTS` registry keys (the same tenant-config keys that
 * route embed traffic). Never fails verification; config read failures
 * report `skipped`.
 */
export function checkLicenseHosts(
  licenseHosts: string[],
): { status: "ok" | "mismatch" | "skipped" } {
  let configured: string[];
  try {
    const keys = new Set<string>();
    for (const k of Object.keys(getDigichatConfig().hosts ?? {})) {
      const n = normalizeEmbedHost(k);
      if (n) keys.add(n);
    }
    for (const k of getEmbedTenantRegistry().keys()) {
      const n = normalizeEmbedHost(k);
      if (n) keys.add(n);
    }
    configured = [...keys];
  } catch {
    return { status: "skipped" };
  }
  store().record.hostsConfigured = configured;
  if (configured.length === 0) return { status: "skipped" };
  const wanted = new Set(
    licenseHosts.map((x) => normalizeEmbedHost(x)).filter((x): x is string => !!x),
  );
  for (const host of wanted) {
    if (configured.includes(host)) return { status: "ok" };
  }
  return { status: "mismatch" };
}

/**
 * Startup verification entry point. Pure local crypto; never touches the
 * network. Never throws — any failure is caught, logged once, and leaves
 * the state serving (`unlicensed`, or `expired` when the credential itself
 * is authentic but past `exp` + leeway). Must run before the
 * `DIGICHAT_AUTO_MIGRATE` early-return in `register()`.
 */
export function initLicenseStateAtStartup(
  opts: { env?: NodeJS.ProcessEnv; nowSec?: number } = {},
): LicenseSnapshot {
  const env = opts.env ?? process.env;
  const startedAt = store().record.startedAt;
  try {
    const token = readLicenseJwt(env);
    if (!token) {
      store().record = {
        ...freshRecord(),
        startedAt,
        detail: "missing_credential",
      };
      console.log("[license] status=unlicensed detail=missing_credential");
      return getLicenseState(opts.nowSec);
    }
    const expectedIssuer = env.DIGIKEY_ISSUER?.trim() || LICENSE_DEFAULT_ISSUER;
    const result = verifyLicenseJwt(token, {
      publicKeyPem: env.DIGIKEY_PUBLIC_KEY_PEM,
      expectedIssuer,
      nowSec: opts.nowSec,
    });
    if (!result.ok) {
      if (result.detail === "expired") {
        // Authentic but lapsed: refuse-at-expiry, still never blocks boot.
        store().record = {
          ...store().record,
          state: "expired",
          detail: "expired",
          rawJwt: token,
        };
        console.warn("[license] status=expired detail=expired");
        return getLicenseState(opts.nowSec);
      }
      store().record = {
        ...store().record,
        state: "unlicensed",
        detail: result.detail,
        rawJwt: null,
      };
      console.warn(`[license] status=unlicensed detail=${result.detail}`);
      return getLicenseState(opts.nowSec);
    }
    const hostsCheck = checkLicenseHosts(result.hosts);
    const detail =
      hostsCheck.status === "mismatch" ? "hosts_mismatch" : "ok";
    if (hostsCheck.status === "mismatch") {
      console.warn(
        `[license] status=valid detail=hosts_mismatch ` +
          `license_id=${result.licenseId} customer=${result.sub} exp=${result.exp}`,
      );
    } else {
      console.log(
        `[license] status=valid detail=ok license_id=${result.licenseId} ` +
          `customer=${result.sub} exp=${result.exp} hosts=${result.hosts.length}`,
      );
    }
    store().record = {
      ...store().record,
      state: "valid",
      detail,
      licenseId: result.licenseId,
      sub: result.sub,
      exp: result.exp,
      rawJwt: token,
    };
    return getLicenseState(opts.nowSec);
  } catch (e) {
    store().record = {
      ...store().record,
      state: "unlicensed",
      detail: "verify_error",
      rawJwt: null,
    };
    console.warn(
      `[license] status=unlicensed detail=verify_error ` +
        `error=${e instanceof Error ? e.message : String(e)}`,
    );
    return getLicenseState(opts.nowSec);
  }
}

/**
 * Synchronous state read for route guards and health. Lazily evaluates the
 * local `exp` backstop on every read so `valid → expired` does not depend
 * on a heartbeat firing.
 */
export function getLicenseState(nowSec?: number): LicenseSnapshot {
  const record = store().record;
  const now = nowSec ?? Math.floor(Date.now() / 1000);
  if (
    record.state === "valid" &&
    typeof record.exp === "number" &&
    now > record.exp + LICENSE_CLOCK_SKEW_LEEWAY_SEC
  ) {
    record.state = "expired";
    record.detail = "expired";
  }
  const { state, detail, licenseId, sub, exp } = record;
  return { state, detail, licenseId, sub, exp };
}

/** Heartbeat outcome application (§4.2). Error outcomes never move the state. */
export function applyHeartbeatResult(
  result: "valid" | "expired" | "denied",
  detail?: string,
  nowSec?: number,
): LicenseSnapshot {
  const record = store().record;
  if (result === "denied") {
    // Terminal within this process: nothing un-latches `revoked`.
    record.state = "revoked";
    record.detail = detail ?? "heartbeat_deny_revoked";
    return getLicenseState(nowSec);
  }
  if (result === "expired") {
    if (record.state !== "revoked") {
      record.state = "expired";
      record.detail = detail ?? "heartbeat_expired";
    }
    return getLicenseState(nowSec);
  }
  // "valid": never un-latches `revoked` or a locally-lapsed `exp`.
  if (record.state === "revoked") return getLicenseState(nowSec);
  const now = nowSec ?? Math.floor(Date.now() / 1000);
  if (
    typeof record.exp === "number" &&
    now > record.exp + LICENSE_CLOCK_SKEW_LEEWAY_SEC
  ) {
    record.state = "expired";
    record.detail = "expired";
    return getLicenseState(nowSec);
  }
  if (record.state !== "unlicensed") {
    record.state = "valid";
    if (record.detail === "heartbeat_expired") record.detail = "ok";
  }
  return getLicenseState(nowSec);
}

/** Internal context for the heartbeat sender (raw JWT stays in-memory). */
export function getHeartbeatContext(): {
  rawJwt: string | null;
  licenseId?: string;
  sub?: string;
  exp?: number;
  licenseStatus: LicenseState;
  hostsConfigured: string[];
  startedAt: string;
} {
  const record = store().record;
  return {
    rawJwt: record.rawJwt,
    licenseId: record.licenseId,
    sub: record.sub,
    exp: record.exp,
    licenseStatus: record.state,
    hostsConfigured: record.hostsConfigured,
    startedAt: record.startedAt,
  };
}

export interface LicenseRefusal {
  status: 503;
  error: "license_revoked" | "license_expired";
  message: string;
}

/** Refusal descriptor for `revoked`/`expired`; `null` means the request proceeds. */
export function getLicenseRefusal(nowSec?: number): LicenseRefusal | null {
  const { state } = getLicenseState(nowSec);
  if (state === "revoked") {
    return {
      status: 503,
      error: "license_revoked",
      message:
        "This deployment's license has been revoked. " +
        "Chat is disabled until the deployment is re-licensed.",
    };
  }
  if (state === "expired") {
    return {
      status: 503,
      error: "license_expired",
      message:
        "This deployment's license has expired. " +
        "Chat is disabled until a renewed license is provisioned.",
    };
  }
  return null;
}

/**
 * Route-guard helper: `Response` for `revoked`/`expired`, `null` otherwise.
 * No `Retry-After` header — the condition is not client-retryable. The body
 * carries no `license_id`, hosts, or infrastructure detail.
 */
export function licenseRefusal(nowSec?: number): Response | null {
  const refusal = getLicenseRefusal(nowSec);
  if (!refusal) return null;
  return new Response(
    JSON.stringify({ error: refusal.error, message: refusal.message }),
    {
      status: refusal.status,
      headers: { "content-type": "application/json" },
    },
  );
}
