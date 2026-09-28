import { describe, it, expect } from "vitest";
import {
  DEFAULT_DIGI_PICK,
  DEFAULT_PROVIDER_PICK,
  DIGI_LAYERS,
  PROVIDER_LAYERS,
  digiSpec,
  pricePick,
  providerSpec,
} from "@/lib/stackCatalog";
import { ragCost } from "@/lib/ragCost";

describe("pricePick", () => {
  it("matches the invoice panel for the default provider stack, plus hosting", () => {
    const price = pricePick(PROVIDER_LAYERS, DEFAULT_PROVIDER_PICK);
    const invoice = ragCost("provider");
    expect(price.setup).toBeCloseTo(invoice.setup, 4);
    // Same usage math, plus the Azure hosting estimate.
    expect(price.monthly).toBeCloseTo(invoice.monthly + 75, 4);
    expect(price.vendors).toEqual(["OpenAI", "Pinecone", "LangSmith", "Azure"]);
  });

  it("runs the default digithings pick at zero", () => {
    const price = pricePick(DIGI_LAYERS, DEFAULT_DIGI_PICK);
    expect(price.setup).toBe(0);
    expect(price.monthly).toBe(0);
    expect(price.vendors).toEqual([]);
  });

  it("rejects unknown picks loudly", () => {
    expect(() => pricePick(PROVIDER_LAYERS, { ...DEFAULT_PROVIDER_PICK, models: "nope" })).toThrow(
      /unknown pick/,
    );
  });
});

describe("configurator specs", () => {
  it("keeps stable box ids on the provider drawing", () => {
    const ids = providerSpec(DEFAULT_PROVIDER_PICK).services.map((s) => s.id);
    for (const id of ["app", "sources", "api", "model", "embed", "memory", "record", "telemetry", "machines", "terms"]) {
      expect(ids).toContain(id);
    }
  });

  it("names the picked providers on the boxes", () => {
    const labels = providerSpec(DEFAULT_PROVIDER_PICK).services.map((s) => s.label);
    expect(labels.some((l) => l.includes("Sol"))).toBe(true);
    expect(labels.some((l) => l.includes("Pinecone"))).toBe(true);
    const cheap = providerSpec({ ...DEFAULT_PROVIDER_PICK, models: "local" });
    expect(cheap.services.find((s) => s.id === "model")?.label).toContain("local");
    expect(cheap.services.find((s) => s.id === "api")?.label).toBe("your API");
  });

  it("keeps stable box ids on the digithings drawing", () => {
    const ids = digiSpec(DEFAULT_DIGI_PICK).services.map((s) => s.id);
    for (const id of ["app", "chat", "graph", "models", "memory", "vault", "traces", "claw", "keys"]) {
      expect(ids).toContain(id);
    }
  });

  it("moves the digithings drawing with the pick", () => {
    const flagged = digiSpec({ ...DEFAULT_DIGI_PICK, models: "sol" });
    expect(flagged.services.find((s) => s.id === "models")?.label).toContain("Sol");
  });
});
