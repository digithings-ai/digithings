import { describe, expect, it } from "vitest";
import {
  inspectTrialProof,
  signTrialProof,
  verifyTrialProof,
  TRIAL_PROOF_EXPIRED_HEADER,
  TRIAL_PROOF_TTL_MS,
} from "./trial-proof";

const SECRET = "test-hmac-secret-3795";
const OTHER_SECRET = "another-hmac-secret-3795";
const HOST = "embed.example.com";

describe("trial-proof", () => {
  it("round-trips a valid token", () => {
    const token = signTrialProof(HOST, SECRET);
    expect(verifyTrialProof(token, SECRET)).toBe(HOST);
  });

  it("rejects a tampered signature", () => {
    const token = signTrialProof(HOST, SECRET);
    const chars = token.split("");
    const mid = Math.floor(chars.length / 2);
    chars[mid] = chars[mid] === "A" ? "B" : "A";
    expect(verifyTrialProof(chars.join(""), SECRET)).toBeNull();
  });

  it("rejects a token verified with the wrong secret", () => {
    const token = signTrialProof(HOST, SECRET);
    expect(verifyTrialProof(token, "wrong-secret")).toBeNull();
  });

  it("rejects an expired token", () => {
    const token = signTrialProof(HOST, SECRET, Date.now() - 1000);
    expect(verifyTrialProof(token, SECRET)).toBeNull();
  });

  it("rejects malformed tokens", () => {
    expect(verifyTrialProof("not-a-token", SECRET)).toBeNull();
    expect(verifyTrialProof("", SECRET)).toBeNull();
    expect(
      verifyTrialProof(
        Buffer.from("only|two").toString("base64url"),
        SECRET,
      ),
    ).toBeNull();
  });

  it("exposes the 600s default TTL", () => {
    expect(TRIAL_PROOF_TTL_MS).toBe(600_000);
  });

  // DIG-4537: the server has to tell an EXPIRED proof from an INVALID one,
  // because only the expired one can be re-minted by the client. The
  // distinction lives in inspectTrialProof; verifyTrialProof keeps its
  // "host or null" contract on top of it.
  describe("inspectTrialProof", () => {
    it("accepts a fresh proof and names its host", () => {
      expect(inspectTrialProof(signTrialProof(HOST, SECRET), SECRET)).toEqual({
        ok: true,
        host: HOST,
      });
    });

    it("reports a proof whose expiry has passed as expired, and keeps its host", () => {
      const token = signTrialProof(HOST, SECRET, Date.now() - 1000);
      expect(inspectTrialProof(token, SECRET)).toEqual({
        ok: false,
        reason: "expired",
        host: HOST,
      });
    });

    it("reports a tampered signature as invalid_signature, not expired", () => {
      const token = signTrialProof(HOST, SECRET);
      const chars = token.split("");
      const mid = Math.floor(chars.length / 2);
      chars[mid] = chars[mid] === "A" ? "B" : "A";
      expect(inspectTrialProof(chars.join(""), SECRET)).toEqual({
        ok: false,
        reason: "invalid_signature",
        host: null,
      });
    });

    it("checks the signature before the expiry, so an expired AND wrongly-signed proof is invalid", () => {
      // Both wrong at once: the token is past its expiry AND was signed with
      // another secret. It must NOT be reported as expired, because that
      // would tell the client to mint a new proof for a token this server
      // never signed.
      const token = signTrialProof(HOST, OTHER_SECRET, Date.now() - 1000);
      expect(inspectTrialProof(token, SECRET)).toEqual({
        ok: false,
        reason: "invalid_signature",
        host: null,
      });
    });

    it("reports a token signed with another secret as invalid_signature", () => {
      const token = signTrialProof(HOST, OTHER_SECRET);
      expect(inspectTrialProof(token, SECRET)).toEqual({
        ok: false,
        reason: "invalid_signature",
        host: null,
      });
    });

    it("reports a malformed token as malformed", () => {
      expect(inspectTrialProof("not-a-token", SECRET)).toEqual({
        ok: false,
        reason: "malformed",
        host: null,
      });
      expect(inspectTrialProof("", SECRET)).toEqual({
        ok: false,
        reason: "malformed",
        host: null,
      });
      expect(
        inspectTrialProof(
          Buffer.from("only|two").toString("base64url"),
          SECRET,
        ),
      ).toEqual({ ok: false, reason: "malformed", host: null });
      expect(
        inspectTrialProof(
          Buffer.from("host|notanumber|sig").toString("base64url"),
          SECRET,
        ),
      ).toEqual({ ok: false, reason: "malformed", host: null });
    });

    it("keeps verifyTrialProof's host-or-null contract on every case", () => {
      expect(verifyTrialProof(signTrialProof(HOST, SECRET), SECRET)).toBe(HOST);
      expect(
        verifyTrialProof(
          signTrialProof(HOST, SECRET, Date.now() - 1000),
          SECRET,
        ),
      ).toBeNull();
      expect(
        verifyTrialProof(signTrialProof(HOST, OTHER_SECRET), SECRET),
      ).toBeNull();
      expect(verifyTrialProof("not-a-token", SECRET)).toBeNull();
    });

    it("names the header the client reads", () => {
      expect(TRIAL_PROOF_EXPIRED_HEADER).toBe("x-embed-trial-proof-expired");
    });
  });
});
