import { describe, expect, it } from "vitest";
import {
  configuredInviteOnlyHosts,
  inviteRequiredButMissing,
  isInviteOnlyDeployment,
} from "./embed-invite-only";

describe("inviteRequiredButMissing", () => {
  it("refuses the OCC host when the token did not resolve the OCC tenant", () => {
    expect(inviteRequiredButMissing("occ.digithings.ai", "embed")).toBe(true);
    expect(inviteRequiredButMissing("OCC.digithings.ai", undefined)).toBe(true);
  });
  it("allows the OCC host with its own tenant", () => {
    expect(inviteRequiredButMissing("occ.digithings.ai", "occ")).toBe(false);
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
  it("adds configured hosts and keeps OCC", () => {
    const hosts = configuredInviteOnlyHosts(RAW);
    expect(hosts.get("example.test.digithings.ai")).toBe("example");
    expect(hosts.get("occ.digithings.ai")).toBe("occ");
  });
  it("cannot reassign the OCC host and ignores malformed input", () => {
    expect(configuredInviteOnlyHosts(JSON.stringify({ x: { host: "occ.digithings.ai" } })).get("occ.digithings.ai")).toBe("occ");
    expect([...configuredInviteOnlyHosts("not json").keys()]).toEqual(["occ.digithings.ai"]);
    expect([...configuredInviteOnlyHosts(JSON.stringify({ "Bad Slug": { host: "a.b.c" } })).keys()]).toEqual([
      "occ.digithings.ai",
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
