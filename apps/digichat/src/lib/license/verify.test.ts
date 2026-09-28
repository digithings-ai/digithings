/**
 * Startup verification cases (§3.1 parse → signature → claims, §3.2 skew).
 * Pure local crypto: every case runs with `fetch` stubbed to throw, proving
 * verification never touches the network.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  LICENSE_CLOCK_SKEW_LEEWAY_SEC,
  verifyLicenseJwt,
} from "./state";
import {
  generateTestKeypair,
  mintLicenseJwt,
  validLicensePayload,
} from "./jwt-fixtures";

const ISSUER = "http://127.0.0.1:8005";

describe("verifyLicenseJwt", () => {
  const keys = generateTestKeypair();
  const other = generateTestKeypair();
  const now = Math.floor(Date.now() / 1000);
  const verify = (token: string, opts: Record<string, unknown> = {}) =>
    verifyLicenseJwt(token, {
      publicKeyPem: keys.publicKeyPem,
      expectedIssuer: ISSUER,
      nowSec: now,
      ...opts,
    });

  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => {
        throw new Error("network must not be touched");
      }),
    );
    return () => {
      vi.unstubAllGlobals();
    };
  });

  it("accepts a well-formed license signed by the configured key", () => {
    const token = mintLicenseJwt(keys.privateKeyPem);
    const result = verify(token);
    expect(result).toMatchObject({
      ok: true,
      licenseId: "lic-test-001",
      sub: "datatap",
    });
    if (result.ok) expect(result.exp).toBeGreaterThan(now);
  });

  it("rejects 2-segment, empty, and non-base64url tokens as malformed_jwt", () => {
    expect(verify("")).toEqual({ ok: false, detail: "malformed_jwt" });
    expect(verify("abc.def")).toEqual({ ok: false, detail: "malformed_jwt" });
    expect(verify("a.b.c.d")).toEqual({ ok: false, detail: "malformed_jwt" });
    expect(verify("!!!.@@@.###")).toEqual({ ok: false, detail: "malformed_jwt" });
  });

  it("rejects decodable-but-not-JSON payloads as bad_json", () => {
    const seg = Buffer.from("not-json", "utf8").toString("base64url");
    const token = mintLicenseJwt(keys.privateKeyPem);
    const sig = token.split(".")[2];
    expect(verify(`${seg}.${seg}.${sig}`)).toEqual({ ok: false, detail: "bad_json" });
  });

  it("rejects alg:none and alg:HS256 without ever touching an HMAC path", () => {
    const payload = validLicensePayload();
    // Unsigned token with alg:none still has three segments.
    const seg = (o: unknown) => Buffer.from(JSON.stringify(o), "utf8").toString("base64url");
    const noneToken = `${seg({ alg: "none" })}.${seg(payload)}.`;
    // Trailing empty signature keeps three segments after split.
    expect(verify(noneToken)).toEqual({ ok: false, detail: "bad_signature" });
    const hsToken = mintLicenseJwt(keys.privateKeyPem, payload, { alg: "HS256" });
    expect(verify(hsToken)).toEqual({ ok: false, detail: "bad_signature" });
  });

  it("rejects tampered payloads and wrong-key signatures as bad_signature", () => {
    const token = mintLicenseJwt(keys.privateKeyPem);
    const [h, , s] = token.split(".");
    const tamperedPayload = Buffer.from(
      JSON.stringify(validLicensePayload({ sub: "mallory" })),
      "utf8",
    ).toString("base64url");
    expect(verify(`${h}.${tamperedPayload}.${s}`)).toEqual({
      ok: false,
      detail: "bad_signature",
    });
    const foreign = mintLicenseJwt(other.privateKeyPem);
    expect(verify(foreign)).toEqual({ ok: false, detail: "bad_signature" });
  });

  it("accepts the second PEM in a two-PEM rotation list", () => {
    const token = mintLicenseJwt(other.privateKeyPem);
    const bundle = `${keys.publicKeyPem}\n${other.publicKeyPem}`;
    const result = verifyLicenseJwt(token, {
      publicKeyPem: bundle,
      expectedIssuer: ISSUER,
      nowSec: now,
    });
    expect(result.ok).toBe(true);
  });

  it("rejects an empty public-key env as no_public_key", () => {
    const token = mintLicenseJwt(keys.privateKeyPem);
    expect(verify(token, { publicKeyPem: "" })).toEqual({
      ok: false,
      detail: "no_public_key",
    });
    expect(verify(token, { publicKeyPem: undefined })).toEqual({
      ok: false,
      detail: "no_public_key",
    });
  });

  it("checks claims in order: exp, aud, iss, kind, hosts, sub/license_id", () => {
    const cases: Array<[Record<string, unknown>, string]> = [
      [{ exp: "never" }, "exp_missing"],
      [{ exp: undefined }, "exp_missing"],
      [{ aud: "digi-ecosystem" }, "aud_mismatch"],
      [{ iss: "http://evil:8005" }, "iss_mismatch"],
      [{ kind: "access" }, "kind_mismatch"],
      [{ hosts: [] }, "hosts_invalid"],
      [{ hosts: "datatapstream.com" }, "hosts_invalid"],
      [{ hosts: [""] }, "hosts_invalid"],
      [{ sub: "", tenant_slug: "" }, "claims_missing"],
      [{ license_id: "", jti: "" }, "claims_missing"],
    ];
    for (const [override, detail] of cases) {
      const token = mintLicenseJwt(keys.privateKeyPem, validLicensePayload(override));
      expect(verify(token), JSON.stringify(override)).toEqual({ ok: false, detail });
    }
  });

  it("accepts tenant_slug and jti mirrors for sub and license_id", () => {
    const payload = validLicensePayload();
    delete payload.sub;
    delete payload.license_id;
    payload.tenant_slug = "mirror-customer";
    payload.jti = "lic-mirror-7";
    const token = mintLicenseJwt(keys.privateKeyPem, payload);
    expect(verify(token)).toMatchObject({
      ok: true,
      licenseId: "lic-mirror-7",
      sub: "mirror-customer",
    });
  });

  it("allows 300s of clock skew on exp and iat, then lapses", () => {
    const skew = LICENSE_CLOCK_SKEW_LEEWAY_SEC;
    expect(skew).toBe(300);
    // exp 4 min in the past still valid.
    const fresh = mintLicenseJwt(
      keys.privateKeyPem,
      validLicensePayload({ exp: now - 240 }),
    );
    expect(verify(fresh).ok).toBe(true);
    // exp 6 min in the past is expired.
    const stale = mintLicenseJwt(
      keys.privateKeyPem,
      validLicensePayload({ exp: now - 360 }),
    );
    expect(verify(stale)).toEqual({ ok: false, detail: "expired" });
    // iat 4 min in the future accepted; far-future iat rejected.
    const early = mintLicenseJwt(
      keys.privateKeyPem,
      validLicensePayload({ iat: now + 240 }),
    );
    expect(verify(early).ok).toBe(true);
    const future = mintLicenseJwt(
      keys.privateKeyPem,
      validLicensePayload({ iat: now + 3600 }),
    );
    expect(verify(future).ok).toBe(false);
  });
});
