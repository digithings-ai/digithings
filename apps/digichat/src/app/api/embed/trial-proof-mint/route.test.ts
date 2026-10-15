import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { verifyTrialProof } from "@/lib/trial-proof";
import { POST } from "./route";

function mintRequest(headers: Record<string, string>, body: unknown): Request {
  return new Request("http://localhost/api/embed/trial-proof-mint", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

describe("trial proof mint endpoint", () => {
  it("refuses anonymous minting", async () => {
    const res = await POST(mintRequest({}, { host: "datatap.stream" }));
    expect(res.status).toBe(401);
  });

  // --- leaf 2 extensions: the credential cases the brief names ---------------
  // Fixtures are values this test invents. None of them is a real secret and
  // none is read from the environment.
  const MONITOR_TOKEN = "test-monitor-secret-0123456789-abcdefghij"; // 43 chars
  const FORGED_TOKEN = "forged-monitor-secret-0123456789-abcdefghi"; // 41 chars
  const SIGNING_SECRET = "test-hmac-secret-3796";

  beforeEach(() => {
    process.env.DIGICHAT_MONITOR_TOKENS = MONITOR_TOKEN;
    process.env.DIGICHAT_TRIAL_PROOF_SECRET = SIGNING_SECRET;
  });

  afterEach(() => {
    delete process.env.DIGICHAT_MONITOR_TOKENS;
    delete process.env.DIGICHAT_TRIAL_PROOF_SECRET;
  });

  it("mints a proof that verifies back to the requested host", async () => {
    const res = await POST(
      mintRequest(
        { "x-embed-monitor-token": MONITOR_TOKEN },
        { host: "datatap.stream" },
      ),
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as { proof?: string };
    expect(typeof body.proof).toBe("string");
    // The load-bearing assertion: the minted token must verify with the SAME
    // secret the verifier side uses. A 200 carrying any string at all would
    // pass a status-only check, so pin the round trip instead.
    expect(verifyTrialProof(body.proof as string, SIGNING_SECRET)).toBe(
      "datatap.stream",
    );
    // ...and must not verify under a different secret (i.e. it is really
    // HMAC-bound, not a bare host echo).
    expect(
      verifyTrialProof(body.proof as string, "a-different-secret"),
    ).toBeNull();
  });

  it("never returns secret material", async () => {
    const res = await POST(
      mintRequest(
        { "x-embed-monitor-token": MONITOR_TOKEN },
        { host: "datatap.stream" },
      ),
    );
    const raw = JSON.stringify(await res.json());
    expect(raw).not.toContain(SIGNING_SECRET);
    expect(raw).not.toContain(MONITOR_TOKEN);
    expect(raw).not.toContain("DIGICHAT_TRIAL_PROOF_SECRET");
  });

  it("refuses a short credential", async () => {
    // Below MIN_MONITOR_TOKEN_LENGTH, so it cannot match any allowlist entry.
    const res = await POST(
      mintRequest({ "x-embed-monitor-token": "too-short" }, { host: "h" }),
    );
    expect(res.status).toBe(401);
  });

  it("refuses a forged credential of a plausible length", async () => {
    // Long enough to clear the length floor, absent from the allowlist: this is
    // the arm a length check alone would let through.
    const res = await POST(
      mintRequest(
        { "x-embed-monitor-token": FORGED_TOKEN },
        { host: "datatap.stream" },
      ),
    );
    expect(res.status).toBe(401);
  });

  it("fails closed when the signing secret is not configured", async () => {
    delete process.env.DIGICHAT_TRIAL_PROOF_SECRET;
    const res = await POST(
      mintRequest(
        { "x-embed-monitor-token": MONITOR_TOKEN },
        { host: "datatap.stream" },
      ),
    );
    // Never 200: minting with an empty secret would yield a token whose
    // signature anyone can recompute.
    expect(res.status).toBe(503);
  });

  it("rejects an empty host once the caller is authenticated", async () => {
    // Proves authentication is decided BEFORE the body is judged: an
    // authenticated caller with a bad body gets 400, and the anonymous case
    // above still gets 401 rather than leaking which one it was.
    const res = await POST(
      mintRequest({ "x-embed-monitor-token": MONITOR_TOKEN }, { host: "   " }),
    );
    expect(res.status).toBe(400);
  });
});