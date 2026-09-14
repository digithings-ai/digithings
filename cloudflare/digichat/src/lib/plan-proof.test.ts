import { describe, expect, it, vi } from "vitest";
import { signPlanProof, verifyPlanProof, isValidPlanTier } from "./plan-proof";

const SECRET = "test-hmac-secret-3662";

describe("plan-proof", () => {
  describe("isValidPlanTier", () => {
    it("accepts valid tiers", () => {
      expect(isValidPlanTier("free")).toBe(true);
      expect(isValidPlanTier("brief")).toBe(true);
      expect(isValidPlanTier("desk")).toBe(true);
      expect(isValidPlanTier("studio")).toBe(true);
      expect(isValidPlanTier("enterprise")).toBe(true);
    });

    it("rejects invalid tiers", () => {
      expect(isValidPlanTier("premium")).toBe(false);
      expect(isValidPlanTier("")).toBe(false);
      expect(isValidPlanTier("FREE")).toBe(false);
      expect(isValidPlanTier("Desk")).toBe(false);
    });
  });

  describe("signPlanProof / verifyPlanProof", () => {
    it("round-trips a valid desk tier", () => {
      const proof = signPlanProof("desk", SECRET);
      expect(verifyPlanProof(proof, SECRET)).toBe("desk");
    });

    it("round-trips all Desk+ tiers", () => {
      for (const tier of ["desk", "studio", "enterprise"] as const) {
        const proof = signPlanProof(tier, SECRET);
        expect(verifyPlanProof(proof, SECRET)).toBe(tier);
      }
    });

    it("round-trips free and brief", () => {
      for (const tier of ["free", "brief"] as const) {
        const proof = signPlanProof(tier, SECRET);
        expect(verifyPlanProof(proof, SECRET)).toBe(tier);
      }
    });

    it("rejects proof with wrong secret", () => {
      const proof = signPlanProof("desk", SECRET);
      expect(verifyPlanProof(proof, "wrong-secret")).toBeNull();
    });

    it("rejects expired proof", () => {
      const proof = signPlanProof("desk", SECRET, Date.now() - 1000);
      expect(verifyPlanProof(proof, SECRET)).toBeNull();
    });

    it("rejects tampered proof", () => {
      const proof = signPlanProof("desk", SECRET);
      // Flip a character in the middle of the proof
      const chars = proof.split("");
      chars[Math.floor(chars.length / 2)] = chars[Math.floor(chars.length / 2)] === "A" ? "B" : "A";
      const tampered = chars.join("");
      expect(verifyPlanProof(tampered, SECRET)).toBeNull();
    });

    it("rejects empty string", () => {
      expect(verifyPlanProof("", SECRET)).toBeNull();
    });

    it("rejects garbage data", () => {
      expect(verifyPlanProof("not-a-valid-proof", SECRET)).toBeNull();
    });

    it("rejects proof with corrupted encoding", () => {
      const proof = signPlanProof("desk", SECRET);
      // Corrupt by inserting invalid base64url chars in the middle
      const mid = Math.floor(proof.length / 2);
      const corrupted = proof.slice(0, mid) + "!!!" + proof.slice(mid + 3);
      expect(verifyPlanProof(corrupted, SECRET)).toBeNull();
    });

    it("produces different proofs for different tiers", () => {
      const desk = signPlanProof("desk", SECRET);
      const studio = signPlanProof("studio", SECRET);
      expect(desk).not.toBe(studio);
    });

    it("produces different proofs at different times", () => {
      const a = signPlanProof("desk", SECRET);
      const b = signPlanProof("desk", SECRET, Date.now() + 1000);
      expect(a).not.toBe(b);
    });
  });
});

describe("resolvePlanTierFromDashboardAccessToken", () => {
  it("returns desk from app_metadata.plan_tier", async () => {
    const { resolvePlanTierFromDashboardAccessToken } = await import("./plan-proof");
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ app_metadata: { plan_tier: "desk" } }),
    });
    await expect(
      resolvePlanTierFromDashboardAccessToken("tok", {
        supabaseUrl: "https://example.supabase.co",
        anonKey: "anon",
        fetchImpl: fetchImpl as unknown as typeof fetch,
      }),
    ).resolves.toBe("desk");
  });

  it("returns null when auth endpoint fails", async () => {
    const { resolvePlanTierFromDashboardAccessToken } = await import("./plan-proof");
    const fetchImpl = vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({}) });
    await expect(
      resolvePlanTierFromDashboardAccessToken("tok", {
        supabaseUrl: "https://example.supabase.co",
        anonKey: "anon",
        fetchImpl: fetchImpl as unknown as typeof fetch,
      }),
    ).resolves.toBeNull();
  });

  it("returns null when url/anon/token missing", async () => {
    const { resolvePlanTierFromDashboardAccessToken } = await import("./plan-proof");
    await expect(
      resolvePlanTierFromDashboardAccessToken("", {
        supabaseUrl: "https://example.supabase.co",
        anonKey: "anon",
      }),
    ).resolves.toBeNull();
  });
});
