import { describe, it, expect } from "vitest";
import {
  DEFAULT_DIGI_PICK,
  DEFAULT_PROVIDER_PICK,
  DIGI_LAYERS,
  PROVIDER_LAYERS,
  digiSpec,
  morphSpec,
  pricePick,
  providerSpec,
} from "@/lib/stackCatalog";
import type { LayerId } from "@/lib/stackCatalog";
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

  it("draws one topology per app on the provider side", () => {
    const support = providerSpec(DEFAULT_PROVIDER_PICK, undefined, { topology: "support" });
    const supportIds = support.services.map((s) => s.id);
    for (const id of ["app", "review", "sources", "api", "model", "email", "launcher", "telemetry", "terms"]) {
      expect(supportIds).toContain(id);
    }
    for (const id of ["embed", "memory", "record", "machines"]) {
      expect(supportIds).not.toContain(id);
    }
    const finance = providerSpec(DEFAULT_PROVIDER_PICK, undefined, { topology: "finance" });
    const financeIds = finance.services.map((s) => s.id);
    for (const id of ["app", "feeds", "filings", "api", "model", "launcher", "record", "telemetry", "terms"]) {
      expect(financeIds).toContain(id);
    }
    for (const id of ["sources", "embed", "memory", "machines", "review", "email"]) {
      expect(financeIds).not.toContain(id);
    }
  });

  it("moves the digithings drawing with the pick", () => {
    const flagged = digiSpec({ ...DEFAULT_DIGI_PICK, models: "sol" });
    expect(flagged.services.find((s) => s.id === "models")?.label).toContain("Sol");
  });

  it("tags one-time lines non-recurring so monthly cells stay monthly", () => {
    const price = pricePick(PROVIDER_LAYERS, DEFAULT_PROVIDER_PICK);
    const setup = price.lines.filter((l) => !l.recurring);
    const monthly = price.lines.filter((l) => l.recurring);
    expect(setup.length).toBeGreaterThan(0);
    expect(setup.reduce((n, l) => n + l.amount, 0)).toBeCloseTo(price.setup, 4);
    expect(monthly.reduce((n, l) => n + l.amount, 0)).toBeCloseTo(price.monthly, 4);
  });
});

describe("morph specs", () => {
  it("starts as the provider copy with identical box ids", () => {
    for (const topology of ["rag", "support", "finance"] as const) {
      const base = providerSpec(DEFAULT_PROVIDER_PICK, undefined, { topology }).services.map((s) => s.id).sort();
      const start = morphSpec(DEFAULT_PROVIDER_PICK, DEFAULT_DIGI_PICK, undefined, { topology }).services.map((s) => s.id).sort();
      expect(start).toEqual(base);
      const labels = morphSpec(DEFAULT_PROVIDER_PICK, DEFAULT_PROVIDER_PICK, undefined, { topology }).services.map((s) => s.label);
      expect(labels.some((l) => l.includes("Sol"))).toBe(true);
    }
  });

  it("swaps the model boxes and the terms together", () => {
    const m = morphSpec(DEFAULT_PROVIDER_PICK, DEFAULT_DIGI_PICK, undefined, {
      replaced: ["models"],
      boxes: ["api", "model", "terms"],
    });
    const byId = Object.fromEntries(m.services.map((s) => [s.id, s.label]));
    expect(byId["api"]).toBe("digillm gateway");
    expect(byId["model"]).toContain("digillm");
    expect(byId["terms"]).toBe("your keys");
    const wire = m.edges.find((e) => e.from === "machines" && e.to === "terms");
    expect(wire?.label).toBe("your keys");
    const support = morphSpec(DEFAULT_PROVIDER_PICK, DEFAULT_DIGI_PICK, undefined, {
      topology: "support",
      replaced: ["models"],
      boxes: ["api", "model", "terms"],
    });
    expect(support.edges.find((e) => e.from === "api" && e.to === "model")?.label).toBe("your rates");
    expect(m.services.find((s) => s.id === "embed")?.label).toBe("embed-3-large");
  });

  it("homes recall and hosting on the RAG drawing", () => {
    const m = morphSpec(DEFAULT_PROVIDER_PICK, DEFAULT_DIGI_PICK, undefined, {
      replaced: ["embeddings", "vector", "hosting"],
      boxes: ["embed", "memory", "record", "machines"],
    });
    const labels = Object.fromEntries(m.services.map((s) => [s.id, s.label]));
    expect(labels["memory"]).toContain("index");
    expect(labels["record"]).toBe("digivault lake");
    expect(labels["machines"]).toBe("your GPU pool");
  });

  it("flips send to the in-graph mail tool on email", () => {
    const m = morphSpec(DEFAULT_PROVIDER_PICK, DEFAULT_DIGI_PICK, undefined, { topology: "support", email: true });
    expect(m.services.find((s) => s.id === "email")?.label).toBe("digigraph mail");
    expect(m.edges.find((e) => e.from === "review" && e.to === "email")?.label).toBe("approved send");
    const plain = morphSpec(DEFAULT_PROVIDER_PICK, DEFAULT_DIGI_PICK, undefined, { topology: "support" });
    expect(plain.services.find((s) => s.id === "email")?.label).toBe("SendGrid");
  });

  it("names the digithings picks on the finished drawing", () => {
    const owned = morphSpec(DEFAULT_PROVIDER_PICK, DEFAULT_DIGI_PICK, undefined, { owned: true });
    expect(owned.groups?.[0]?.label).toBe("digithings · no vendors · no meters");
    expect(owned.edges.find((e) => e.from === "sources")?.label).toBe("your connectors");
    const leaving = morphSpec(DEFAULT_PROVIDER_PICK, DEFAULT_DIGI_PICK);
    expect(leaving.groups?.[0]?.label).not.toContain("digithings");
  });

  it("files the finance archive in digivault", () => {
    const m = morphSpec(DEFAULT_PROVIDER_PICK, DEFAULT_DIGI_PICK, undefined, {
      topology: "finance",
      replaced: ["hosting"],
      boxes: ["record"],
    });
    expect(m.services.find((s) => s.id === "record")?.label).toBe("digivault archive");
    expect(m.services.find((s) => s.id === "launcher")?.label).toBe("nightly runner");
  });

  it("flips the finance runner a beat before the archive", () => {
    const opts = { topology: "finance" as const, replaced: ["hosting"] as LayerId[] };
    const runner = morphSpec(DEFAULT_PROVIDER_PICK, DEFAULT_DIGI_PICK, undefined, {
      ...opts,
      boxes: ["launcher"],
    });
    expect(runner.services.find((s) => s.id === "launcher")?.label).toBe("digiclaw runner");
    expect(runner.services.find((s) => s.id === "record")?.label).toBe("research archive");
  });
});
