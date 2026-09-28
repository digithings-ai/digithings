/**
 * License state machine (§4): startup init, lazy expiry, latch
 * transitions, refusal shape, and the advisory hosts comparison (§3.5).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/deploy-config/loader", () => ({
  getDigichatConfig: vi.fn(),
}));

vi.mock("@/lib/embed-tenants", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/lib/embed-tenants")>();
  return { ...actual, getEmbedTenantRegistry: vi.fn() };
});

import { getDigichatConfig } from "@/lib/deploy-config/loader";
import { getEmbedTenantRegistry } from "@/lib/embed-tenants";
import {
  applyHeartbeatResult,
  checkLicenseHosts,
  getLicenseRefusal,
  getLicenseState,
  initLicenseStateAtStartup,
  licenseRefusal,
  readLicenseJwt,
  resetLicenseStateForTests,
} from "./state";
import {
  generateTestKeypair,
  mintLicenseJwt,
  validLicensePayload,
} from "./jwt-fixtures";

const ISSUER = "http://127.0.0.1:8005";

function stubHosts(configHosts: string[], registryHosts: string[]) {
  vi.mocked(getDigichatConfig).mockReturnValue({
    hosts: Object.fromEntries(configHosts.map((h) => [h, {}])),
  } as unknown as ReturnType<typeof getDigichatConfig>);
  vi.mocked(getEmbedTenantRegistry).mockReturnValue(
    new Map(registryHosts.map((h) => [h, {}])) as unknown as ReturnType<
      typeof getEmbedTenantRegistry
    >,
  );
}

describe("readLicenseJwt", () => {
  it("returns null when neither var is set", () => {
    expect(readLicenseJwt({} as NodeJS.ProcessEnv)).toBeNull();
  });

  it("prefers DIGICHAT_LICENSE_FILE when readable, else falls back to inline env", async () => {
    const { mkdtempSync, writeFileSync, rmSync } = await import("node:fs");
    const { tmpdir } = await import("node:os");
    const { join } = await import("node:path");
    const dir = mkdtempSync(join(tmpdir(), "lic-test-"));
    try {
      const file = join(dir, "license.jwt");
      writeFileSync(file, "  file.jwt.token\n", "utf8");
      expect(
        readLicenseJwt({
          DIGICHAT_LICENSE_FILE: file,
          DIGICHAT_LICENSE_JWT: "inline.jwt.token",
        } as NodeJS.ProcessEnv),
      ).toBe("file.jwt.token");
      // Unreadable path falls back to inline env.
      expect(
        readLicenseJwt({
          DIGICHAT_LICENSE_FILE: join(dir, "missing.jwt"),
          DIGICHAT_LICENSE_JWT: "inline.jwt.token",
        } as NodeJS.ProcessEnv),
      ).toBe("inline.jwt.token");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("initLicenseStateAtStartup", () => {
  const keys = generateTestKeypair();
  const now = Math.floor(Date.now() / 1000);
  let logSpy: ReturnType<typeof vi.spyOn>;
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    resetLicenseStateForTests();
    stubHosts([], []);
    logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    logSpy.mockRestore();
    warnSpy.mockRestore();
    resetLicenseStateForTests();
  });

  function envFor(token: string | null) {
    return {
      DIGICHAT_LICENSE_JWT: token ?? "",
      DIGIKEY_PUBLIC_KEY_PEM: keys.publicKeyPem,
      DIGIKEY_ISSUER: ISSUER,
    } as unknown as NodeJS.ProcessEnv;
  }

  it("is unlicensed with missing_credential when no credential is present", () => {
    const snap = initLicenseStateAtStartup({ env: {} as NodeJS.ProcessEnv });
    expect(snap).toMatchObject({ state: "unlicensed", detail: "missing_credential" });
  });

  it("never throws on a broken credential and keeps serving state", () => {
    const snap = initLicenseStateAtStartup({
      env: envFor("not-a-jwt"),
      nowSec: now,
    });
    expect(snap.state).toBe("unlicensed");
    expect(getLicenseState().state).toBe("unlicensed");
  });

  it("verifies a good credential and reports valid", () => {
    const token = mintLicenseJwt(keys.privateKeyPem);
    const snap = initLicenseStateAtStartup({ env: envFor(token), nowSec: now });
    expect(snap).toMatchObject({ state: "valid", detail: "ok" });
    expect(snap.licenseId).toBe("lic-test-001");
    expect(snap.sub).toBe("datatap");
  });

  it("boots expired (never blocking) when the credential is authentic but lapsed", () => {
    const token = mintLicenseJwt(
      keys.privateKeyPem,
      validLicensePayload({ exp: now - 3600 }),
    );
    const snap = initLicenseStateAtStartup({ env: envFor(token), nowSec: now });
    expect(snap).toMatchObject({ state: "expired", detail: "expired" });
  });

  it("never logs the raw JWT", () => {
    const token = mintLicenseJwt(keys.privateKeyPem);
    initLicenseStateAtStartup({ env: envFor(token), nowSec: now });
    const logged = [...logSpy.mock.calls, ...warnSpy.mock.calls]
      .map((c) => c.map(String).join(" "))
      .join("\n");
    expect(logged).not.toContain(token);
    expect(logged).not.toContain(keys.publicKeyPem);
  });
});

describe("state machine transitions", () => {
  const keys = generateTestKeypair();
  const now = Math.floor(Date.now() / 1000);
  let warnSpy: ReturnType<typeof vi.spyOn>;
  let logSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    resetLicenseStateForTests();
    stubHosts([], []);
    logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const token = mintLicenseJwt(keys.privateKeyPem);
    initLicenseStateAtStartup({
      env: {
        DIGICHAT_LICENSE_JWT: token,
        DIGIKEY_PUBLIC_KEY_PEM: keys.publicKeyPem,
        DIGIKEY_ISSUER: ISSUER,
      } as unknown as NodeJS.ProcessEnv,
      nowSec: now,
    });
  });

  afterEach(() => {
    logSpy.mockRestore();
    warnSpy.mockRestore();
    resetLicenseStateForTests();
  });

  it("boots valid and flips to expired lazily without a heartbeat", () => {
    expect(getLicenseState(now).state).toBe("valid");
    const exp = getLicenseState(now).exp ?? now;
    expect(getLicenseState(exp + 301).state).toBe("expired");
    expect(getLicenseRefusal(exp + 301)?.error).toBe("license_expired");
  });

  it("latches revoked on an explicit deny and stays terminal on later valid", () => {
    applyHeartbeatResult("denied", "heartbeat_deny_revoked");
    expect(getLicenseState()).toMatchObject({
      state: "revoked",
      detail: "heartbeat_deny_revoked",
    });
    applyHeartbeatResult("valid");
    expect(getLicenseState().state).toBe("revoked");
    applyHeartbeatResult("expired");
    expect(getLicenseState().state).toBe("revoked");
  });

  it("records unknown_license denies distinctly but still refuses", () => {
    applyHeartbeatResult("denied", "heartbeat_deny_unknown");
    expect(getLicenseState()).toMatchObject({
      state: "revoked",
      detail: "heartbeat_deny_unknown",
    });
    expect(getLicenseRefusal()?.error).toBe("license_revoked");
  });

  it("resetLicenseStateForTests clears the globalThis latch", () => {
    applyHeartbeatResult("denied");
    resetLicenseStateForTests();
    expect(getLicenseState()).toMatchObject({
      state: "unlicensed",
      detail: "missing_credential",
    });
  });
});

describe("licenseRefusal", () => {
  beforeEach(() => {
    resetLicenseStateForTests();
    stubHosts([], []);
    vi.spyOn(console, "log").mockImplementation(() => {});
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    resetLicenseStateForTests();
  });

  it("returns null for unlicensed and valid (requests proceed)", () => {
    expect(licenseRefusal()).toBeNull();
    applyHeartbeatResult("valid");
    // Unlicensed record stays unlicensed on a valid outcome (no credential).
    expect(licenseRefusal()).toBeNull();
  });

  it("returns 503 JSON without Retry-After for revoked", async () => {
    applyHeartbeatResult("denied", "heartbeat_deny_revoked");
    const res = licenseRefusal();
    expect(res).not.toBeNull();
    expect(res?.status).toBe(503);
    expect(res?.headers.get("content-type")).toContain("application/json");
    expect(res?.headers.get("retry-after")).toBeNull();
    expect(await res?.json()).toMatchObject({ error: "license_revoked" });
  });

  it("returns 503 license_expired for expired", async () => {
    applyHeartbeatResult("expired");
    const res = licenseRefusal();
    expect(res?.status).toBe(503);
    expect(await res?.json()).toMatchObject({ error: "license_expired" });
  });
});

describe("checkLicenseHosts (advisory)", () => {
  beforeEach(() => {
    resetLicenseStateForTests();
    vi.spyOn(console, "log").mockImplementation(() => {});
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    resetLicenseStateForTests();
  });

  it("matches exact hosts and subsets without mismatch", () => {
    stubHosts(["datatapstream.com"], []);
    expect(checkLicenseHosts(["datatapstream.com"]).status).toBe("ok");
    // Container serves a subset of the licensed hosts: still ok.
    expect(
      checkLicenseHosts(["datatapstream.com", "other.example.com"]).status,
    ).toBe("ok");
  });

  it("normalizes case, trailing dots, and ports", () => {
    stubHosts(["DataTapStream.COM."], []);
    expect(checkLicenseHosts(["datatapstream.com:3000"]).status).toBe("ok");
  });

  it("reads the embed tenant registry as a configured-host source", () => {
    stubHosts([], ["tenant.example.com"]);
    expect(checkLicenseHosts(["tenant.example.com"]).status).toBe("ok");
  });

  it("reports mismatch on disjoint sets but leaves the state valid", () => {
    stubHosts(["unrelated.example.com"], []);
    expect(checkLicenseHosts(["datatapstream.com"]).status).toBe("mismatch");
    // The mismatch is advisory: init still reports valid.
    const keys = generateTestKeypair();
    const token = mintLicenseJwt(keys.privateKeyPem);
    const snap = initLicenseStateAtStartup({
      env: {
        DIGICHAT_LICENSE_JWT: token,
        DIGIKEY_PUBLIC_KEY_PEM: keys.publicKeyPem,
        DIGIKEY_ISSUER: ISSUER,
      } as unknown as NodeJS.ProcessEnv,
    });
    expect(snap.state).toBe("valid");
    expect(snap.detail).toBe("hosts_mismatch");
  });

  it("skips silently when no hosts are configured", () => {
    stubHosts([], []);
    expect(checkLicenseHosts(["datatapstream.com"]).status).toBe("skipped");
  });

  it("skips when the config cannot be read", () => {
    vi.mocked(getDigichatConfig).mockImplementation(() => {
      throw new Error("no config");
    });
    expect(checkLicenseHosts(["datatapstream.com"]).status).toBe("skipped");
  });
});
