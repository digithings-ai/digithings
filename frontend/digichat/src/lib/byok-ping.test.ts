import { describe, expect, it, vi } from "vitest";
import { byokActivationGate, pingByokKey } from "@/lib/byok-ping";

describe("byok-ping activation gate", () => {
  it("blocks activation until a successful ping", () => {
    expect(byokActivationGate(null)).not.toBeNull();
    expect(byokActivationGate({ ok: false, error: "denied" })).toBe("denied");
    expect(byokActivationGate({ ok: true })).toBeNull();
  });
});

describe("pingByokKey requireModel option", () => {
  it("still runs the client-side model-format check by default (requireModel omitted)", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    try {
      const result = await pingByokKey("sk-ant-test", "anthropic", "");
      expect(result.ok).toBe(false);
      expect(result.error).toContain("Model is required");
      // Refused before ever reaching the network — this is the pre-existing
      // client-side pre-check, still the default with opts omitted.
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("skips the client-side model-format check when requireModel is false, and surfaces models in the result", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          models: [{ id: "claude-3-5-haiku-20241022", label: "claude-3-5-haiku-20241022" }],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    try {
      const result = await pingByokKey("sk-ant-test", "anthropic", "", { requireModel: false });
      expect(fetchSpy).toHaveBeenCalled();
      expect(result.ok).toBe(true);
      expect(result.models).toEqual([
        { id: "claude-3-5-haiku-20241022", label: "claude-3-5-haiku-20241022" },
      ]);
    } finally {
      fetchSpy.mockRestore();
    }
  });
});
