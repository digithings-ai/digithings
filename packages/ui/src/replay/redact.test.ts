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

describe("redactString: header schemes and provider shapes", () => {
  it("replaces Authorization values for every scheme, including helpdesk Token tokens", () => {
    const raw = [
      "Authorization: Token token=helpdesk-plain-9f3c2a",
      'curl -H "Authorization: Basic dXNlcjpwYXNzd29yZA=="',
      '{"headers":{"Authorization":"Token token=helpdesk-json-9f3c2a"}}',
      "see Token token=helpdesk-prose-9f3c2a in the log",
    ].join("\n");
    const out = redactString(raw);
    for (const secret of [
      "helpdesk-plain-9f3c2a",
      "dXNlcjpwYXNzd29yZA==",
      "helpdesk-json-9f3c2a",
      "helpdesk-prose-9f3c2a",
    ]) {
      expect(out).not.toContain(secret);
    }
    expect(out).toContain("in the log");
  });

  it("replaces labeled passwords and client secrets in prose", () => {
    const out = redactString(
      "password=plain-pass-9f3c2a client_secret: plain-cs-9f3c2a token=plain-tok-9f3c2a",
    );
    expect(out).not.toContain("plain-pass-9f3c2a");
    expect(out).not.toContain("plain-cs-9f3c2a");
    expect(out).not.toContain("plain-tok-9f3c2a");
  });

  it("replaces common provider token shapes", () => {
    // Built at runtime so the fixtures are not real-looking secrets in source.
    const shapes = [
      "gh" + "p_" + "A1b2C3d4".repeat(5),
      "github" + "_pat_" + "A1b2C3d4".repeat(4),
      "xo" + "xb-" + "1234567890-abcdefghij",
      "AK" + "IA" + "ABCDEFGHIJKLMNOP",
      "AI" + "za" + "A1b2C3d4E5".repeat(3) + "A1b2C",
      "gl" + "pat-" + "A1b2C3d4".repeat(3),
    ];
    const out = redactString(shapes.join(" "));
    for (const shape of shapes) expect(out).not.toContain(shape);
  });

  it("keeps token counts", () => {
    expect(redactString("max_tokens: 4000, input_tokens=1200")).toBe(
      "max_tokens: 4000, input_tokens=1200",
    );
  });
});

describe("redactValue", () => {
  it("replaces keys that end in token, secret, password or key names", () => {
    const out = redactValue({
      token: "t-plain-9f3c2a",
      authToken: "a-plain-9f3c2a",
      client_secret: "c-plain-9f3c2a",
      privateKey: "p-plain-9f3c2a",
      max_tokens: 4000,
    });
    expect(JSON.stringify(out)).not.toMatch(/plain-9f3c2a/);
    expect(out.max_tokens).toBe(4000);
  });

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
