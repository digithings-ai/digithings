import { describe, it, expect } from "vitest";
import { APP_PRESETS } from "@/lib/appPresets";
import { DIGI_LAYERS, PROVIDER_LAYERS, digiSpec, pricePick, providerSpec } from "@/lib/stackCatalog";

describe("app presets", () => {
  it("declares three apps with the RAG loop default first", () => {
    expect(APP_PRESETS.map((a) => a.id)).toEqual(["rag", "support", "finance"]);
  });

  it("keeps workloads sane and positive", () => {
    for (const app of APP_PRESETS) {
      const w = app.workload;
      expect(w.corpusGB).toBeGreaterThan(0);
      expect(w.queriesPerDay).toBeGreaterThan(0);
      expect(w.chatInTokensPerQuery).toBeGreaterThan(0);
    }
  });

  it("references only real option ids in defaults and recommended picks", () => {
    for (const app of APP_PRESETS) {
      for (const layer of PROVIDER_LAYERS) {
        expect(layer.options.map((o) => o.id)).toContain(app.providerDefaults[layer.id]);
      }
      for (const layer of DIGI_LAYERS) {
        for (const pick of [app.digiDefaults, app.recommended]) {
          expect(layer.options.map((o) => o.id)).toContain(pick[layer.id]);
        }
      }
    }
  });

  it("dims only boxes that exist on the digithings drawing", () => {
    const ids = digiSpec(
      { models: "local", embeddings: "local", vector: "self", telemetry: "digismith", hosting: "own" },
    ).services.map((s) => s.id);
    for (const app of APP_PRESETS) {
      for (const id of app.dimmedDigi) expect(ids).toContain(id);
    }
  });

  it("prices every app without NaNs on both sides", () => {
    for (const app of APP_PRESETS) {
      const provider = pricePick(PROVIDER_LAYERS, app.providerDefaults, app.workload);
      const digi = pricePick(DIGI_LAYERS, app.recommended, app.workload);
      for (const n of [provider.setup, provider.monthly, digi.setup, digi.monthly]) {
        expect(Number.isFinite(n)).toBe(true);
        expect(n).toBeGreaterThanOrEqual(0);
      }
      expect(provider.monthly).toBeGreaterThan(digi.monthly);
    }
  });

  it("builds per-app specs with the app's top-box labels", () => {
    const finance = APP_PRESETS.find((a) => a.id === "finance")!;
    const spec = digiSpec(finance.digiDefaults, finance.workload, { appLabel: finance.digiApp });
    expect(spec.services.find((s) => s.id === "app")?.label).toBe("digiquant pipeline");
    const left = providerSpec(finance.providerDefaults, finance.workload, { appLabel: finance.providerApp });
    expect(left.services.find((s) => s.id === "app")?.label).toBe("research agent");
  });

  it("lights only boxes the app actually draws", () => {
    for (const app of APP_PRESETS) {
      const drawn = new Set(
        providerSpec(app.providerDefaults, app.workload, {
          appLabel: app.providerApp,
          sourcesLabel: app.providerSources,
          topology: app.topology,
        }).services.map((s) => s.id),
      );
      for (const step of app.leftSteps) {
        for (const id of step.ids) {
          expect(drawn.has(id) || id === "platform").toBe(true);
        }
      }
    }
  });

  it("walks four morph beats per app against drawn boxes", () => {
    for (const app of APP_PRESETS) {
      expect(app.morphSteps).toHaveLength(4);
      expect(app.morphCaption.length).toBeGreaterThan(0);
      const drawn = new Set(
        providerSpec(app.providerDefaults, app.workload, {
          appLabel: app.providerApp,
          sourcesLabel: app.providerSources,
          topology: app.topology,
        }).services.map((s) => s.id),
      );
      for (const step of app.morphSteps) {
        for (const id of step.ids) {
          expect(drawn.has(id)).toBe(true);
        }
      }
    }
  });

  it("cuts priced rows on every morph beat except send", () => {
    const layersOf = (id: string) =>
      new Set(APP_PRESETS.find((a) => a.id === id)!.morphSteps.flatMap((s) => s.layers));
    expect(layersOf("rag")).toEqual(new Set(["models", "embeddings", "vector", "telemetry", "hosting"]));
    expect(layersOf("support")).toEqual(new Set(["models", "telemetry", "hosting"]));
    expect(layersOf("finance")).toEqual(new Set(["models", "hosting", "telemetry"]));
    const send = APP_PRESETS.find((a) => a.id === "support")!.morphSteps.find((s) => s.email)!;
    expect(send.layers).toEqual([]);
    expect(send.ids).toContain("email");
  });

  it("draws the support review gate and finance twin sources", () => {
    const support = APP_PRESETS.find((a) => a.id === "support")!;
    const left = providerSpec(support.providerDefaults, support.workload, {
      sourcesLabel: support.providerSources,
      topology: support.topology,
    });
    const ids = left.services.map((s) => s.id);
    expect(ids).toContain("review");
    expect(left.services.find((s) => s.id === "sources")?.label).toBe("tickets + docs");
    expect(left.services.find((s) => s.id === "email")?.label).toBe("SendGrid");
    const finance = APP_PRESETS.find((a) => a.id === "finance")!;
    const fin = providerSpec(finance.providerDefaults, finance.workload, { topology: finance.topology });
    const finIds = fin.services.map((s) => s.id);
    expect(finIds).toContain("feeds");
    expect(finIds).toContain("filings");
    expect(finIds).not.toContain("sources");
    const rag = APP_PRESETS.find((a) => a.id === "rag")!;
    const plain = providerSpec(rag.providerDefaults, rag.workload, {});
    expect(plain.services.map((s) => s.id)).not.toContain("review");
  });
});
