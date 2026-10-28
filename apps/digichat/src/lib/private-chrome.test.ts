import { describe, expect, it } from "vitest";
import {
  PRIVATE_HEADER_TITLE,
  PRIVATE_PLACEHOLDER,
  PRIVATE_SUGGESTIONS,
  PRIVATE_WELCOME,
  privateSessionChrome,
} from "./private-chrome";

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
    for (const name of ["occ", "zammad", "digithings", "digichat"]) {
      expect(all).not.toContain(name);
    }
  });
});
