import { describe, expect, it } from "vitest";
import {
  configuredInviteOnlyHosts,
  inviteRequiredButMissing,
  isInviteOnlyDeployment,
} from "./embed-invite-only";

describe("inviteRequiredButMissing", () => {
  it("refuses the tenantb host when the token did not resolve the tenantb tenant", () => {
    expect(inviteRequiredButMissing("tenantb.example.com", "embed")).toBe(true);
    expect(inviteRequiredButMissing("tenantb.example.com", undefined)).toBe(true);
  });
  it("allows the tenantb host with its own tenant", () => {
    expect(inviteRequiredButMissing("tenantb.example.com", "tenantb")).toBe(false);
  });
  it("leaves other hosts alone", () => {
    expect(inviteRequiredButMissing("digithings.ai", "embed")).toBe(false);
    expect(inviteRequiredButMissing("digiquant.io", "embed")).toBe(false);
    expect(inviteRequiredButMissing(null, "embed")).toBe(false);
  });
});

describe("configured invite-only hosts (DIGICHAT_INVITE_PAGES)", () => {
  const RAW = JSON.stringify({
    example: { host: "example.test.digithings.ai", keyEnv: "EXAMPLE_INVITE_KEY" },
  });
  it("adds configured hosts and keeps tenantb", () => {
    const hosts = configuredInviteOnlyHosts(RAW);
    expect(hosts.get("example.test.digithings.ai")).toBe("example");
    expect(hosts.get("tenantb.example.com")).toBe("tenantb");
  });
  it("cannot reassign the tenantb host and ignores malformed input", () => {
    expect(configuredInviteOnlyHosts(JSON.stringify({ x: { host: "tenantb.example.com" } })).get("tenantb.example.com")).toBe("tenantb");
    expect([...configuredInviteOnlyHosts("not json").keys()]).toEqual(["tenantb.example.com"]);
    expect([...configuredInviteOnlyHosts(JSON.stringify({ "Bad Slug": { host: "a.b.c" } })).keys()]).toEqual([
      "tenantb.example.com",
    ]);
  });
  it("refuses a configured host without its own tenant, from the env", () => {
    const prev = process.env.DIGICHAT_INVITE_PAGES;
    process.env.DIGICHAT_INVITE_PAGES = RAW;
    try {
      expect(inviteRequiredButMissing("example.test.digithings.ai", "embed")).toBe(true);
      expect(inviteRequiredButMissing("example.test.digithings.ai", "example")).toBe(false);
      expect(isInviteOnlyDeployment(null, "example")).toBe(true);
    } finally {
      if (prev === undefined) delete process.env.DIGICHAT_INVITE_PAGES;
      else process.env.DIGICHAT_INVITE_PAGES = prev;
    }
  });
});
