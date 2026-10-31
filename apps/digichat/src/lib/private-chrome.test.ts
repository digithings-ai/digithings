import { describe, expect, it } from "vitest";
import {
  PRIVATE_HEADER_TITLE,
  PRIVATE_PLACEHOLDER,
  PRIVATE_SUGGESTIONS,
  PRIVATE_WELCOME,
  isPrivateUrlParam,
  privateFirstPaintTenant,
  privateSessionChrome,
} from "./private-chrome";
import { DEFAULT_EMBED_TENANT_CONFIG, type EmbedTenantClientConfig } from "./embed-client-config";

const tenant = {
  welcome: "Ask about Acme Desk.",
  placeholder: "Ask about Acme Desk",
  suggestions: ["Search Acme tickets"],
  headerTitle: "Acme Desk Help",
};

describe("privateSessionChrome", () => {
  it("leaves the tenant's copy alone outside a private session", () => {
    expect(privateSessionChrome(false, tenant)).toBe(tenant);
  });

  it("swaps in generic support copy in a private session", () => {
    const out = privateSessionChrome(true, tenant);
    expect(out).toEqual({
      welcome: PRIVATE_WELCOME,
      placeholder: PRIVATE_PLACEHOLDER,
      suggestions: [...PRIVATE_SUGGESTIONS],
      headerTitle: PRIVATE_HEADER_TITLE,
    });
    expect(JSON.stringify(out)).not.toMatch(/acme/i);
  });

  it("does not add a header title where the tenant had none", () => {
    expect(privateSessionChrome(true, { ...tenant, headerTitle: undefined }).headerTitle).toBe(
      undefined,
    );
  });

  it("generic copy names no product or ticketing system", () => {
    const all = [PRIVATE_WELCOME, PRIVATE_PLACEHOLDER, PRIVATE_HEADER_TITLE, ...PRIVATE_SUGGESTIONS]
      .join(" ")
      .toLowerCase();
    for (const name of ["occ", "digithings", "digichat"]) {
      expect(all).not.toContain(name);
    }
  });
});

describe("privateFirstPaintTenant", () => {
  const cfg: EmbedTenantClientConfig = {
    ...DEFAULT_EMBED_TENANT_CONFIG,
    slug: "fixture",
    title: "Acme Desk Help",
    welcome: "Ask about Acme Desk.",
    welcomeBody: ["Acme Desk answers from its help centre."],
    placeholder: "Ask about Acme Desk",
    suggestions: ["Search Acme tickets"],
    privateMode: true,
  };

  it("swaps every tenant string for the generic copy on a private page", () => {
    const out = privateFirstPaintTenant(cfg, true);
    expect(out).toMatchObject({
      title: PRIVATE_HEADER_TITLE,
      welcome: PRIVATE_WELCOME,
      placeholder: PRIVATE_PLACEHOLDER,
      suggestions: [...PRIVATE_SUGGESTIONS],
      privateMode: true,
      slug: "fixture",
    });
    expect(out.welcomeBody).toBeUndefined();
    expect(JSON.stringify(out)).not.toContain("Acme");
  });

  it("keeps a missing title missing", () => {
    expect(privateFirstPaintTenant({ ...cfg, title: undefined }, true).title).toBeUndefined();
  });

  it("returns the config untouched without ?private=1 or without the tenant opt-in", () => {
    expect(privateFirstPaintTenant(cfg, false)).toBe(cfg);
    const optedOut = { ...cfg, privateMode: undefined };
    expect(privateFirstPaintTenant(optedOut, true)).toBe(optedOut);
  });

  it("reads only an exact ?private=1", () => {
    expect(isPrivateUrlParam("1")).toBe(true);
    expect(isPrivateUrlParam(["1", "0"])).toBe(true);
    for (const v of ["0", "true", "", undefined, ["0", "1"]]) expect(isPrivateUrlParam(v)).toBe(false);
  });
});
