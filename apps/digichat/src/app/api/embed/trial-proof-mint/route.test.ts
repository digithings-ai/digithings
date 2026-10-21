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
    const res = await POST(mintRequest({}, { host: "tenant.example.com" }));
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
        { host: "tenant.example.com" },
      ),
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as { proof?: string };
    expect(typeof body.proof).toBe("string");
    // The load-bearing assertion: the minted token must verify with the SAME
    // secret the verifier side uses. A 200 carrying any string at all would
    // pass a status-only check, so pin the round trip instead.
    expect(verifyTrialProof(body.proof as string, SIGNING_SECRET)).toBe(
      "tenant.example.com",
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
        { host: "tenant.example.com" },
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
        { host: "tenant.example.com" },
      ),
    );
    expect(res.status).toBe(401);
  });

  it("fails closed when the signing secret is not configured", async () => {
    delete process.env.DIGICHAT_TRIAL_PROOF_SECRET;
    const res = await POST(
      mintRequest(
        { "x-embed-monitor-token": MONITOR_TOKEN },
        { host: "tenant.example.com" },
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

  // --- DIG-4526: the host-scoped tenant credential ---------------------------
  // The tenant credential is bound to ONE host. The monitor credential stays
  // exactly as it was. These cases pin both halves, and the negative arms
  // prove that nothing is minted when the credential does not cover the host.
  describe("host-scoped tenant credential", () => {
    const TENANT_TOKEN = "test-tenant-secret-0123456789-abcdefghij";
    const OTHER_TENANT_TOKEN = "test-tenant-secret-9876543210-abcdefghij";

    beforeEach(() => {
      process.env.DIGICHAT_TENANT_MINT_CREDENTIALS =
        `tenant.example.com=${TENANT_TOKEN},other.example.com=${OTHER_TENANT_TOKEN}`;
    });

    afterEach(() => {
      delete process.env.DIGICHAT_TENANT_MINT_CREDENTIALS;
    });

    it("mints a proof that verifies back to the tenant's own host only", async () => {
      const res = await POST(
        mintRequest(
          { "x-embed-tenant-mint-token": TENANT_TOKEN },
          { host: "tenant.example.com" },
        ),
      );
      expect(res.status).toBe(200);
      const body = (await res.json()) as { proof?: string };
      expect(typeof body.proof).toBe("string");
      // The round trip, not the status: a proof for a DIFFERENT host would
      // still be a 200.
      expect(verifyTrialProof(body.proof as string, SIGNING_SECRET)).toBe(
        "tenant.example.com",
      );
      expect(
        verifyTrialProof(body.proof as string, "a-different-secret"),
      ).toBeNull();

      // The other tenant's credential mints for its own host and no other.
      const other = await POST(
        mintRequest(
          { "x-embed-tenant-mint-token": OTHER_TENANT_TOKEN },
          { host: "other.example.com" },
        ),
      );
      expect(other.status).toBe(200);
      const otherBody = (await other.json()) as { proof?: string };
      expect(verifyTrialProof(otherBody.proof as string, SIGNING_SECRET)).toBe(
        "other.example.com",
      );
    });

    it("refuses a tenant credential that is not scoped to the requested host, and mints nothing", async () => {
      const res = await POST(
        mintRequest(
          { "x-embed-tenant-mint-token": TENANT_TOKEN },
          { host: "other.example.com" },
        ),
      );
      expect(res.status).toBe(401);
      // The load-bearing negative: a refusal that still returned a proof
      // would satisfy the status check and defeat the whole point.
      const raw = JSON.stringify(await res.json());
      expect(raw).not.toContain("proof");
      expect(raw).not.toContain(TENANT_TOKEN);
      expect(raw).not.toContain(SIGNING_SECRET);
    });

    it("refuses a tenant credential when the host list is not configured", async () => {
      delete process.env.DIGICHAT_TENANT_MINT_CREDENTIALS;
      const res = await POST(
        mintRequest(
          { "x-embed-tenant-mint-token": TENANT_TOKEN },
          { host: "tenant.example.com" },
        ),
      );
      expect(res.status).toBe(401);
      expect(JSON.stringify(await res.json())).not.toContain("proof");
    });

    it("never accepts the tenant credential as a monitor credential", async () => {
      // The tenant credential is in a different variable and a different
      // header, so it is not on the monitor allowlist and cannot be replayed
      // as one.
      const res = await POST(
        mintRequest(
          { "x-embed-monitor-token": TENANT_TOKEN },
          { host: "tenant.example.com" },
        ),
      );
      expect(res.status).toBe(401);
      expect(JSON.stringify(await res.json())).not.toContain("proof");
    });

    it("leaves the monitor path working exactly as it was", async () => {
      // The monitor mechanism does not change: the same allowlist entry still
      // authenticates, and the monitor still mints for the host it names.
      const res = await POST(
        mintRequest(
          { "x-embed-monitor-token": MONITOR_TOKEN },
          { host: "tenant.example.com" },
        ),
      );
      expect(res.status).toBe(200);
      const body = (await res.json()) as { proof?: string };
      expect(verifyTrialProof(body.proof as string, SIGNING_SECRET)).toBe(
        "tenant.example.com",
      );
    });

    it("does not fall through to the monitor rule when the tenant header is present", async () => {
      // A tenant header decides the whole request. If the route fell through
      // to the monitor rule, a bad tenant credential paired with a good
      // monitor one would mint, and the two mechanisms would mix.
      const res = await POST(
        mintRequest(
          {
            "x-embed-tenant-mint-token": "not-a-valid-tenant-secret",
            "x-embed-monitor-token": MONITOR_TOKEN,
          },
          { host: "tenant.example.com" },
        ),
      );
      expect(res.status).toBe(401);
      expect(JSON.stringify(await res.json())).not.toContain("proof");
    });

    it("does not fall through to the monitor rule when the tenant header is present but empty", async () => {
      // An EMPTY tenant header is still a PRESENT tenant header: the rule is
      // that the header's presence decides the request, not its value. If the
      // route treated an empty value as absent, a caller could send an empty
      // tenant header alongside a good monitor token and mint on the monitor
      // path, which is exactly the fall-through the two mechanisms must not
      // have.
      const res = await POST(
        mintRequest(
          {
            "x-embed-tenant-mint-token": "",
            "x-embed-monitor-token": MONITOR_TOKEN,
          },
          { host: "tenant.example.com" },
        ),
      );
      expect(res.status).toBe(401);
      expect(JSON.stringify(await res.json())).not.toContain("proof");
    });

    it("mints for the canonical host of the pair, not for the spelling in the request", async () => {
      const res = await POST(
        mintRequest(
          { "x-embed-tenant-mint-token": TENANT_TOKEN },
          { host: "TENANT.EXAMPLE.COM" },
        ),
      );
      expect(res.status).toBe(200);
      const body = (await res.json()) as { proof?: string };
      // The CANONICAL host of the pair is what gets signed, so the request can
      // never choose what is minted.
      expect(verifyTrialProof(body.proof as string, SIGNING_SECRET)).toBe(
        "tenant.example.com",
      );
    });

    it("mints when the tenant's backend names the host as an origin URL", async () => {
      // The shape a tenant's backend actually sends. The route compares the
      // CANONICAL form of both sides — the same helper the chat route uses to
      // verify the proof — so a legitimate caller is not refused, and the
      // round trip still holds.
      const res = await POST(
        mintRequest(
          { "x-embed-tenant-mint-token": TENANT_TOKEN },
          { host: "https://tenant.example.com" },
        ),
      );
      expect(res.status).toBe(200);
      const body = (await res.json()) as { proof?: string };
      expect(verifyTrialProof(body.proof as string, SIGNING_SECRET)).toBe(
        "tenant.example.com",
      );
    });

    it("mints when the pair names the host as an origin URL", async () => {
      // The other direction: the operator wrote the pair as a URL and the
      // caller sends the bare host. The credential binds the HOST, so both
      // spellings bind the same host.
      process.env.DIGICHAT_TENANT_MINT_CREDENTIALS =
        `https://tenant.example.com=${TENANT_TOKEN}`;
      const res = await POST(
        mintRequest(
          { "x-embed-tenant-mint-token": TENANT_TOKEN },
          { host: "tenant.example.com" },
        ),
      );
      expect(res.status).toBe(200);
      const body = (await res.json()) as { proof?: string };
      expect(verifyTrialProof(body.proof as string, SIGNING_SECRET)).toBe(
        "tenant.example.com",
      );
    });

    it("refuses a host that does not canonicalise, and mints nothing", async () => {
      // Neither side can be compared, so there is no host to sign.
      const res = await POST(
        mintRequest(
          { "x-embed-tenant-mint-token": TENANT_TOKEN },
          { host: "https://" },
        ),
      );
      expect(res.status).toBe(401);
      const raw = JSON.stringify(await res.json());
      expect(raw).not.toContain("proof");
    });

    it("never returns secret material on the tenant path", async () => {
      const res = await POST(
        mintRequest(
          { "x-embed-tenant-mint-token": TENANT_TOKEN },
          { host: "tenant.example.com" },
        ),
      );
      const raw = JSON.stringify(await res.json());
      expect(raw).not.toContain(TENANT_TOKEN);
      expect(raw).not.toContain(SIGNING_SECRET);
      expect(raw).not.toContain("DIGICHAT_TENANT_MINT_CREDENTIALS");
      expect(raw).not.toContain("DIGICHAT_TRIAL_PROOF_SECRET");
    });
  });
});