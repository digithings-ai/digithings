import { describe, expect, it } from "vitest";
import { REDACTED, redactString, redactValue } from "./redact";

const JWT =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U";

describe("redactString", () => {
  it("replaces digikey, provider, and bearer tokens", () => {
    const raw = [
      "dgk_live_TESTSECRET99",
      "digi_live_TESTSECRET99",
      "dgs_live_TESTSECRET99",
      "sk-ant-TESTSECRET99",
      "sk-or-TESTSECRET99",
      `Bearer ${JWT}`,
    ].join(" ");
    const out = redactString(raw);
    expect(out).not.toContain("TESTSECRET99");
    expect(out).not.toContain(JWT);
    expect(out).toContain(REDACTED);
  });

  it("replaces JSON-quoted header names", () => {
    const out = redactString('{"X-Embed-Token": "embed-plain-9f3c2a", "q": "book"}');
    expect(out).not.toContain("embed-plain-9f3c2a");
    expect(out).toContain("book");
  });

  it("replaces labeled headers and query secrets that have no token prefix", () => {
    const out = redactString(
      "X-Embed-Token: embed-plain-9f3c2a\ninvite_key=invite-plain-9f3c2a\nhttps://desk.example/cb?token=query-plain-9f3c2a&ok=1",
    );
    expect(out).not.toContain("embed-plain-9f3c2a");
    expect(out).not.toContain("invite-plain-9f3c2a");
    expect(out).not.toContain("query-plain-9f3c2a");
    expect(out).toContain("ok=1");
    expect(out).toContain("?token=[redacted]");
  });
});

describe("redactValue", () => {
  it("replaces sensitive object keys entirely", () => {
    const out = redactValue({
      authorization: `Bearer ${JWT}`,
      inviteKey: "invite-plain-9f3c2a",
      "X-Api-Key": "sk-ant-TESTSECRET99",
      note: "visible",
    });
    expect(out.authorization).toBe(REDACTED);
    expect(out.inviteKey).toBe(REDACTED);
    expect(out["X-Api-Key"]).toBe(REDACTED);
    expect(out.note).toBe("visible");
    expect(JSON.stringify(out)).not.toContain(JWT);
    expect(JSON.stringify(out)).not.toContain("TESTSECRET99");
    expect(JSON.stringify(out)).not.toContain("invite-plain-9f3c2a");
  });
});
