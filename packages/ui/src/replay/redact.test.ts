import { describe, expect, it } from "vitest";
import { REDACTED, redactString, redactValue } from "./redact";

const HEX48 = "a1b2c3d4".repeat(6);
const HEX40 = "0123456789".repeat(4);
const HEX64 = "f".repeat(64);

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

  it("replaces a standalone 48-hex invite key and leaves other hex lengths", () => {
    const out = redactString(
      `invite ${HEX48} sha ${HEX40} long ${HEX64} https://desk.example/embed?token=${HEX48}&ok=1`,
    );
    expect(out).not.toContain(HEX48);
    expect(out).toContain(HEX40);
    expect(out).toContain(HEX64);
    expect(out).toContain("?token=[redacted]");
    expect(out).toContain("ok=1");
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

describe("redactString: cookies, sessions, DSNs, and prose", () => {
  it("replaces cookie and session values in a raw HTTP dump, keeping the labels", () => {
    const raw = [
      "> Cookie: session=cookie-plain-9f3c2a; csrftoken=csrf-plain-9f3c2a",
      "< Set-Cookie: sid=sid-plain-9f3c2a; Path=/",
      "> X-Digichat-Session: 8f14e45f-ceea-467a-9575-1cba2e2c9f11",
    ].join("\n");
    const out = redactString(raw);
    for (const secret of [
      "cookie-plain-9f3c2a",
      "csrf-plain-9f3c2a",
      "sid-plain-9f3c2a",
      "8f14e45f-ceea",
    ]) {
      expect(out).not.toContain(secret);
    }
    expect(out).toContain("Cookie: [redacted]");
    expect(out).toContain("Set-Cookie: [redacted]");
  });

  it("replaces the password in a DSN and keeps the host", () => {
    const out = redactString('"dbUrl": "postgres://app:dsn-plain-9f3c2a@db.internal:5432/app"');
    expect(out).not.toContain("dsn-plain-9f3c2a");
    expect(out).toContain("postgres://app:[redacted]@db.internal:5432/app");
  });

  it("leaves prose that only mentions Authorization", () => {
    const prose =
      "Authorization: the request is allowed once the user signs in. After that the flow continues.";
    expect(redactString(prose)).toBe(prose);
  });

  it("keeps the Authorization label and replaces the credential", () => {
    expect(redactString("Authorization: Basic dXNlcjpwYXNzd29yZA==")).toBe(
      "Authorization: [redacted]",
    );
    expect(redactString("authorization=abc123def456")).toBe("authorization=[redacted]");
  });
});

describe("redactString is idempotent", () => {
  it("leaves an already redacted value alone", () => {
    for (const input of [
      '"api_key": "supersecretvalue"',
      "password=hunter22",
      "token: abcdef123",
    ]) {
      const once = redactString(input);
      expect(redactString(once)).toBe(once);
    }
  });
});

describe("redactValue", () => {
  it("replaces keys that end in token, secret, password or key names", () => {
    const out = redactValue({
      token: "t-plain-9f3c2a",
      authToken: "a-plain-9f3c2a",
      client_secret: "c-plain-9f3c2a",
      privateKey: "p-plain-9f3c2a",
      secretKey: "s-plain-9f3c2a",
      credentials: "cr-plain-9f3c2a",
      max_tokens: 4000,
    });
    expect(JSON.stringify(out)).not.toMatch(/plain-9f3c2a/);
    expect(out.max_tokens).toBe(4000);
  });

  it("replaces a session key and leaves sessions alone", () => {
    const out = redactValue({ session: "sess-plain-9f3c2a", sessions: "keep-me" });
    expect(out.session).toBe(REDACTED);
    expect(out.sessions).toBe("keep-me");
  });

  it("replaces a Signature query value", () => {
    const url = redactString("https://files.example/o?Signature=sig-plain-9f3c2a&ok=1");
    expect(url).not.toContain("sig-plain-9f3c2a");
    expect(url).toContain("?Signature=[redacted]");
    expect(url).toContain("ok=1");
  });

  it("replaces a Key-Pair-Id query value", () => {
    const url = redactString("https://files.example/o?Key-Pair-Id=pair-plain-9f3c2a&ok=1");
    expect(url).not.toContain("pair-plain-9f3c2a");
    expect(url).toContain("?Key-Pair-Id=[redacted]");
    expect(url).toContain("ok=1");
  });

  it("leaves a link's closing parenthesis outside a query secret", () => {
    const out = redactString("(https://files.example/o?token=tok-plain-9f3c2a)");
    expect(out).toBe("(https://files.example/o?token=[redacted])");
  });

  it("leaves a link's closing parenthesis outside a query secret before a space", () => {
    const out = redactString("(https://files.example/o?token=tok-plain-9f3c2a) ");
    expect(out).toBe("(https://files.example/o?token=[redacted]) ");
  });

  it("redacts a query secret whose value contains a closing parenthesis", () => {
    const out = redactString("https://files.example/o?token=tok)plain-9f3c2a&ok=1");
    expect(out).not.toContain("tok)plain-9f3c2a");
    expect(out).toBe("https://files.example/o?token=[redacted]&ok=1");
  });

  it("redacts a query secret whose tail follows a closing parenthesis", () => {
    // The character after the parenthesis looks like part of a secret, so the
    // value continues and the tail is part of the secret too.
    const out = redactString("?token=abcdef123456)+GHIJKLMNOP");
    expect(out).not.toContain("GHIJKLMNOP");
    expect(out).toBe("?token=[redacted]");
  });

  it("keeps sentence punctuation outside a query secret", () => {
    const out = redactString("(https://files.example/o?token=tok-plain-9f3c2a).");
    expect(out).toBe("(https://files.example/o?token=[redacted]).");
  });

  it("keeps markdown emphasis after a query secret outside the value", () => {
    const out = redactString("[a](https://x.example/?token=abcdef123456)**bold**");
    expect(out).toBe("[a](https://x.example/?token=[redacted])**bold**");
  });

  it("eats a word that follows a closing parenthesis with the value", () => {
    // The `)` is ambiguous, so the secret wins: the word goes with it.
    const out = redactString("See [f](https://x.example/?token=abcdef123456)and more");
    expect(out).toBe("See [f](https://x.example/?token=[redacted] more");
  });

  it("leaves a closing backtick outside a session value", () => {
    const out = redactString("`session=sess-plain-9f3c2a`");
    expect(out).toBe("`session=[redacted]`");
  });

  it("keeps a code span's closing backtick outside a session value", () => {
    const out = redactString("`session=abcdefgh` is set.");
    expect(out).toBe("`session=[redacted]` is set.");
  });

  it("redacts a session value whose value contains a backtick", () => {
    const out = redactString("`session=sess`plain-9f3c2a`");
    expect(out).not.toContain("sess`plain-9f3c2a");
    expect(out).toBe("`session=[redacted]`");
  });

  it("redacts a session value whose tail follows a backtick", () => {
    // The character after the backtick looks like part of a secret, so the
    // value continues and the tail is part of the secret too.
    const out = redactString("session=abcdef123456`+GHIJKLMNOP");
    expect(out).not.toContain("GHIJKLMNOP");
    expect(out).toBe("session=[redacted]");
  });

  it("keeps prose punctuation outside a session value", () => {
    const out = redactString("`session=abcdefgh`, and more");
    expect(out).toBe("`session=[redacted]`, and more");
  });

  it("redacts a session value of 500 characters whole", () => {
    const out = redactString(`session=${"a".repeat(500)}`);
    expect(out).not.toContain("a".repeat(500));
    expect(out).toBe("session=[redacted]");
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
