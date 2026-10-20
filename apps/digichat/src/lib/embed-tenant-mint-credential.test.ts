import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  EMBED_TENANT_MINT_TOKEN_HEADER,
  TENANT_MINT_CREDENTIALS_ENV,
  tenantMintCredentialHost,
  tenantMintHostMatches,
} from "@/lib/embed-tenant-mint-credential";

const here = dirname(fileURLToPath(import.meta.url));

// Fixtures are values this test invents. None of them is a real secret and
// none is read from the environment.
const TENANT_TOKEN = "test-tenant-secret-0123456789-abcdefghij";
const OTHER_TOKEN = "test-tenant-secret-9876543210-abcdefghij";

describe("tenant mint credential", () => {
  beforeEach(() => {
    process.env[TENANT_MINT_CREDENTIALS_ENV] =
      `tenant.example.com=${TENANT_TOKEN},other.example.com=${OTHER_TOKEN}`;
  });

  afterEach(() => {
    delete process.env[TENANT_MINT_CREDENTIALS_ENV];
  });

  it("uses a header and a variable of its own", () => {
    // One header with two meanings would make a tenant token a monitor token:
    // the chat route reads x-embed-monitor-token as a quota bypass, so a
    // tenant credential in that header would be a monitor credential there.
    // The tenant credential needs its own header and its own variable.
    expect(EMBED_TENANT_MINT_TOKEN_HEADER).toBe("x-embed-tenant-mint-token");
    expect(EMBED_TENANT_MINT_TOKEN_HEADER).not.toBe("x-embed-monitor-token");
    expect(EMBED_TENANT_MINT_TOKEN_HEADER).not.toBe("x-embed-token");
    expect(EMBED_TENANT_MINT_TOKEN_HEADER).not.toBe("x-embed-chat-token");
    expect(TENANT_MINT_CREDENTIALS_ENV).toBe("DIGICHAT_TENANT_MINT_CREDENTIALS");
    expect(TENANT_MINT_CREDENTIALS_ENV).not.toBe("DIGICHAT_MONITOR_TOKENS");
  });

  it("binds a presented credential to its host", () => {
    expect(tenantMintCredentialHost(TENANT_TOKEN)).toBe("tenant.example.com");
    expect(tenantMintCredentialHost(OTHER_TOKEN)).toBe("other.example.com");
  });

  it("reads the list at call time, so a deploy secret needs no restart", () => {
    delete process.env[TENANT_MINT_CREDENTIALS_ENV];
    expect(tenantMintCredentialHost(TENANT_TOKEN)).toBeNull();
    process.env[TENANT_MINT_CREDENTIALS_ENV] =
      `late.example.com=${TENANT_TOKEN}`;
    expect(tenantMintCredentialHost(TENANT_TOKEN)).toBe("late.example.com");
  });

  it("trims both sides of a pair", () => {
    process.env[TENANT_MINT_CREDENTIALS_ENV] =
      `  tenant.example.com =  ${TENANT_TOKEN}  `;
    expect(tenantMintCredentialHost(TENANT_TOKEN)).toBe("tenant.example.com");
  });

  it("splits a pair at the FIRST = so a token may contain one", () => {
    const tokenWithEquals = "test-tenant-secret-with=equals-inside";
    process.env[TENANT_MINT_CREDENTIALS_ENV] =
      `tenant.example.com=${tokenWithEquals}`;
    expect(tenantMintCredentialHost(tokenWithEquals)).toBe("tenant.example.com");
  });

  it("refuses an unknown credential", () => {
    expect(tenantMintCredentialHost("not-a-known-tenant-secret")).toBeNull();
    expect(tenantMintCredentialHost(null)).toBeNull();
    expect(tenantMintCredentialHost("")).toBeNull();
  });

  it("refuses a host listed twice", () => {
    // One pair binds one host. A host that appears twice is ambiguous, so the
    // route refuses to mint for it instead of picking one of the two.
    process.env[TENANT_MINT_CREDENTIALS_ENV] =
      `tenant.example.com=${TENANT_TOKEN},tenant.example.com=${OTHER_TOKEN}`;
    expect(tenantMintCredentialHost(TENANT_TOKEN)).toBeNull();
    expect(tenantMintCredentialHost(OTHER_TOKEN)).toBeNull();
  });

  it("refuses one token listed under two hosts", () => {
    // The same token under two hosts would let a tenant mint for whichever
    // host it named, so an ambiguous list binds nothing.
    process.env[TENANT_MINT_CREDENTIALS_ENV] =
      `tenant.example.com=${TENANT_TOKEN},other.example.com=${TENANT_TOKEN}`;
    expect(tenantMintCredentialHost(TENANT_TOKEN)).toBeNull();
  });

  it("skips a half-written pair instead of letting it authorise", () => {
    process.env[TENANT_MINT_CREDENTIALS_ENV] =
      `broken,tenant.example.com=${TENANT_TOKEN},=orphan-token,host-only=`;
    expect(tenantMintCredentialHost(TENANT_TOKEN)).toBe("tenant.example.com");
    expect(tenantMintCredentialHost("orphan-token")).toBeNull();
    expect(tenantMintCredentialHost("")).toBeNull();
  });

  it("returns the CANONICAL host of the pair, not the operator's spelling", () => {
    // The proof is minted for the canonical host, so the operator's spelling
    // is not what gets signed: the consume side compares the canonical form.
    process.env[TENANT_MINT_CREDENTIALS_ENV] =
      `Tenant.Example.com=${TENANT_TOKEN}`;
    expect(tenantMintCredentialHost(TENANT_TOKEN)).toBe("tenant.example.com");
  });

  it("returns the canonical host of a pair written as an origin URL", () => {
    // An operator may write the pair either way; the credential binds the
    // HOST, not the spelling, so both spellings bind the same host.
    process.env[TENANT_MINT_CREDENTIALS_ENV] =
      `https://tenant.example.com=${TENANT_TOKEN}`;
    expect(tenantMintCredentialHost(TENANT_TOKEN)).toBe("tenant.example.com");
  });

  it("binds nothing when the pair's host does not canonicalise", () => {
    // There is no host to compare against and no host to sign, so the pair
    // authorises nothing rather than something undefined.
    process.env[TENANT_MINT_CREDENTIALS_ENV] = `https://=${TENANT_TOKEN}`;
    expect(tenantMintCredentialHost(TENANT_TOKEN)).toBeNull();
  });

  it("refuses one host listed twice in two spellings", () => {
    // The same host written two ways is still the same host, so the list is
    // ambiguous and binds nothing.
    process.env[TENANT_MINT_CREDENTIALS_ENV] =
      `tenant.example.com=${TENANT_TOKEN},https://tenant.example.com=${OTHER_TOKEN}`;
    expect(tenantMintCredentialHost(TENANT_TOKEN)).toBeNull();
    expect(tenantMintCredentialHost(OTHER_TOKEN)).toBeNull();
  });

  it("matches a requested host against the bound host in canonical form", () => {
    expect(tenantMintHostMatches("tenant.example.com", "tenant.example.com")).toBe(
      true,
    );
    expect(tenantMintHostMatches("  TENANT.EXAMPLE.COM ", "tenant.example.com")).toBe(
      true,
    );
    expect(tenantMintHostMatches("other.example.com", "tenant.example.com")).toBe(
      false,
    );
    expect(tenantMintHostMatches("", "tenant.example.com")).toBe(false);
    expect(tenantMintHostMatches("tenant.example.com", "")).toBe(false);
  });

  it("matches a host named as an origin URL against a bare bound host", () => {
    // The shape a tenant's backend actually sends. A trimmed, lower-cased
    // compare would refuse this legitimate caller; the canonical compare the
    // consume side uses accepts it.
    expect(
      tenantMintHostMatches("https://tenant.example.com", "tenant.example.com"),
    ).toBe(true);
    expect(
      tenantMintHostMatches("tenant.example.com", "https://tenant.example.com"),
    ).toBe(true);
  });

  it("matches nothing when either host does not canonicalise", () => {
    expect(tenantMintHostMatches("https://", "tenant.example.com")).toBe(false);
    expect(tenantMintHostMatches("tenant.example.com", "https://")).toBe(false);
  });

  it("leaves the monitor allowlist reading only its own variable", () => {
    // The monitor mechanism does not change: its helper must not learn the
    // tenant variable or the tenant header, or a tenant credential would
    // become a monitor credential.
    const source = readFileSync(join(here, "embed-monitor-token.ts"), "utf8");
    expect(source).toContain("DIGICHAT_MONITOR_TOKENS");
    expect(source).not.toContain("TENANT_MINT_CREDENTIALS");
    expect(source).not.toContain("x-embed-tenant-mint-token");
  });
});
