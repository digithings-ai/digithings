import { describe, expect, it } from "vitest";
import {
  signTrialProof,
  verifyTrialProof,
  TRIAL_PROOF_TTL_MS,
} from "./trial-proof";

const SECRET = "test-hmac-secret-3795";
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
});
