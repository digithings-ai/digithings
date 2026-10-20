import { beforeEach, describe, expect, it, vi } from "vitest";
import { onRequestPost } from "./contact";

// Minimal EventContext stand-in: the function only reads `request` and `env`.
function ctx(
  body: unknown,
  headers: Record<string, string> = {},
  env: Record<string, unknown> = {},
  url = "http://localhost/api/contact",
): { request: Request; env: Record<string, unknown> } {
  return {
    request: new Request(url, {
      method: "POST",
      headers: { "content-type": "application/json", ...headers },
      body: typeof body === "string" ? body : JSON.stringify(body),
    }),
    env,
  };
}

const VALID = { email: "someone@example.com", message: "Tell me about digiquant integration." };

describe("POST /api/contact", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(console, "log").mockImplementation(() => {});
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("accepts a well-formed submission and records it", async () => {
    const res = await onRequestPost(ctx(VALID));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
    expect(console.log).toHaveBeenCalledTimes(1);
    const logged = JSON.parse((console.log as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(logged).toMatchObject({ kind: "contact", email: VALID.email, message: VALID.message });
  });

  it("rejects a cross-site origin", async () => {
    // Non-localhost host so the localhost short-circuit does not apply — this
    // is the case the check actually guards.
    const res = await onRequestPost(
      ctx(VALID, { origin: "https://evil.example" }, {}, "https://digithings.ai/api/contact"),
    );
    expect(res.status).toBe(403);
    expect((await res.json()).error).toMatch(/Cross-site/);
  });

  it("accepts a same-site origin on a real host", async () => {
    const res = await onRequestPost(
      ctx(VALID, { origin: "https://digithings.ai" }, {}, "https://digithings.ai/api/contact"),
    );
    expect(res.status).toBe(200);
  });

  it("rejects a malformed email", async () => {
    const res = await onRequestPost(ctx({ ...VALID, email: "not-an-email" }));
    expect(res.status).toBe(400);
    expect((await res.json()).error).toMatch(/email/i);
  });

  it("rejects a too-short message", async () => {
    const res = await onRequestPost(ctx({ ...VALID, message: "hi" }));
    expect(res.status).toBe(400);
  });

  it("rejects a non-JSON body", async () => {
    const res = await onRequestPost(ctx("just text"));
    expect(res.status).toBe(400);
    expect((await res.json()).error).toMatch(/JSON/);
  });

  it("strips CR/LF from the submitted email so no header can be injected", async () => {
    // A newline-smuggling attempt in the address must never reach the log or
    // the notification's Reply-To as multiple header lines.
    const res = await onRequestPost(
      ctx({ email: "a@b.co\nBcc: victim@example.com", message: "hello there friend" }),
    );
    // Collapsed to one line, this is no longer a valid address, so it is rejected.
    expect(res.status).toBe(400);
    expect(console.log).not.toHaveBeenCalled();
  });

  it("sends a notification email when the binding is present, as the site not the visitor", async () => {
    const send = vi.fn().mockResolvedValue(undefined);
    const res = await onRequestPost(ctx(VALID, {}, { CONTACT_EMAIL: { send } }));
    expect(res.status).toBe(200);
    expect(send).toHaveBeenCalledTimes(1);
    const msg = send.mock.calls[0][0];
    expect(msg.to).toBe("contact@digithings.ai");
    expect(msg.from).toBe("site@digithings.ai");
    expect(msg.replyTo).toBe(VALID.email);
  });

  it("still returns 200 when the notification send fails — the record is the durable part", async () => {
    const send = vi.fn().mockRejectedValue(new Error("boom"));
    const res = await onRequestPost(ctx(VALID, {}, { CONTACT_EMAIL: { send } }));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
    expect(console.error).toHaveBeenCalled();
  });
});
