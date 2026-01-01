/**
 * Durable gated claims (client-repos epic, U1). The Worker forwards KV
 * `gated-claims` as DIGICHAT_GATED_CLAIMS; these claims must keep a gated
 * host denied after a restart even when the tenant registry is missing or
 * unreadable. Example hosts only; no model calls.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  classifyTenantChatPath,
  gatedTenantClaims,
  isClaimedGatedHost,
  parseDurableGatedClaims,
  resetGatedTenantCacheForTests,
} from "./tenant-chrome";
import { resetEmbedTenantRegistryForTests } from "@/lib/embed-tenants";
import { inviteRequiredButMissing, isInviteOnlyDeployment } from "@/lib/embed-invite-only";

const HOST = "gated.example.com";
const CLAIM = { slug: "example", chatSlug: "example", host: HOST };

function reset() {
  vi.unstubAllEnvs();
  resetGatedTenantCacheForTests();
  resetEmbedTenantRegistryForTests();
}

beforeEach(() => {
  reset();
  vi.stubEnv("DIGICHAT_INVITE_PAGES", "");
  vi.stubEnv("DIGICHAT_EMBED_TENANTS", "");
});
afterEach(reset);

describe("parseDurableGatedClaims", () => {
  it("normalizes valid rows", () => {
    expect(parseDurableGatedClaims(JSON.stringify([{ slug: "Example", chatSlug: "example", host: "Gated.Example.com" }]))).toEqual([CLAIM]);
  });
  it("skips invalid rows one by one", () => {
    const raw = JSON.stringify([{ slug: "bad slug", host: HOST }, { slug: "x" }, { slug: "y", host: "not a host" }, 7, CLAIM]);
    expect(parseDurableGatedClaims(raw)).toEqual([CLAIM]);
  });
  it("adds nothing for blank, non-JSON or non-array values", () => {
    for (const raw of [undefined, "", "{", "{}", "null"]) expect(parseDurableGatedClaims(raw)).toEqual([]);
  });
});

describe("DIGICHAT_GATED_CLAIMS feeds the gated claims", () => {
  it("denies a claimed host without its own tenant when the registry is empty", () => {
    expect(inviteRequiredButMissing(HOST, null)).toBe(false);
    resetGatedTenantCacheForTests();
    vi.stubEnv("DIGICHAT_GATED_CLAIMS", JSON.stringify([CLAIM]));
    expect(isClaimedGatedHost(HOST)).toBe(true);
    expect(inviteRequiredButMissing(HOST, null)).toBe(true);
    expect(inviteRequiredButMissing(HOST, "house")).toBe(true);
    expect(inviteRequiredButMissing(HOST, "example")).toBe(false);
    expect(isInviteOnlyDeployment(HOST, null)).toBe(true);
  });

  it("denies when the registry is unreadable", () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", "{not json");
    vi.stubEnv("DIGICHAT_GATED_CLAIMS", JSON.stringify([CLAIM]));
    expect(inviteRequiredButMissing(HOST, null)).toBe(true);
  });

  it("keeps a claimed /chat/<slug> gated with no document", () => {
    vi.stubEnv("DIGICHAT_GATED_CLAIMS", JSON.stringify([CLAIM]));
    expect(classifyTenantChatPath("/chat/example", null)).toEqual({ kind: "gated-unknown", chatSlug: "example" });
    expect(classifyTenantChatPath("/chat/example", [])).toEqual({ kind: "gated-unknown", chatSlug: "example" });
  });

  it("only accumulates: a later blank or broken value removes nothing", () => {
    vi.stubEnv("DIGICHAT_GATED_CLAIMS", JSON.stringify([CLAIM]));
    const before = gatedTenantClaims().length;
    vi.stubEnv("DIGICHAT_GATED_CLAIMS", "");
    expect(gatedTenantClaims().length).toBe(before);
    vi.stubEnv("DIGICHAT_GATED_CLAIMS", "{broken");
    expect(inviteRequiredButMissing(HOST, null)).toBe(true);
  });

  it("dedupes repeated values", () => {
    vi.stubEnv("DIGICHAT_GATED_CLAIMS", JSON.stringify([CLAIM, CLAIM]));
    const n = gatedTenantClaims().length;
    vi.stubEnv("DIGICHAT_GATED_CLAIMS", JSON.stringify([CLAIM]));
    expect(gatedTenantClaims().length).toBe(n);
    expect(gatedTenantClaims().filter((c) => c.host === HOST)).toHaveLength(1);
  });
});
