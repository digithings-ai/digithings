import { describe, expect, it } from "vitest";
import type { StageName } from "@/lib/run-snapshot";
import { renderToStaticMarkup } from "react-dom/server";
import { StepOutputPanel } from "./StageCard";
import { STAGE_COPY } from "./stage-copy";
import { documentsForStep, loadStepOutput, matchDocumentKey, stepIsMapped, type StepOutputRead } from "./step-output";
import type { OfficialFailure, OfficialSuccess } from "@/lib/official-api";

type Get = (path: string, query?: Record<string, string>) => Promise<OfficialSuccess | OfficialFailure>;

const ok = (body: unknown): OfficialSuccess => ({ ok: true, body });
const fail = (reason: string): OfficialFailure => ({ ok: false, reason });

describe("step document mapping", () => {
  it("maps every stage-copy sub-step, including the ones a reader named", () => {
    for (const [stage, copy] of Object.entries(STAGE_COPY) as [StageName, (typeof STAGE_COPY)[StageName]][]) {
      for (const step of copy.steps) expect(stepIsMapped(stage, step)).toBe(true);
    }
    expect(matchDocumentKey("Inputs", "Preflight / market data", "inputs")).toBe(true);
    expect(matchDocumentKey("Inputs", "Preflight / market data", "attention-plan")).toBe(false);
    expect(matchDocumentKey("Research", "Alt-data", "alt-cta-positioning")).toBe(true);
    expect(matchDocumentKey("Research", "Alt-data", "macro")).toBe(false);
    expect(matchDocumentKey("Synthesis", "Consolidate bias", "bias-row")).toBe(true);
    expect(matchDocumentKey("Synthesis", "Consolidate bias", "digest")).toBe(false);
    expect(matchDocumentKey("Synthesis", "Daily digest", "digest-delta")).toBe(true);
  });

  it("keeps only that step's rows for the recorded date, and prefers content", () => {
    const rows = [
      { document_key: "alt-cta-positioning", title: "CTA", date: "2026-10-01", content: "Positioning was light.", payload: { body: "ignored" } },
      { document_key: "alt-news", title: "News", date: "2026-10-01", content: null, payload: { body: "Headline from the payload." } },
      { document_key: "macro", title: "Macro", date: "2026-10-01", content: "Not alt-data.", payload: null },
      { document_key: "alt-cta-positioning", title: "Old", date: "2026-09-30", content: "Yesterday.", payload: null },
      {
        document_key: "bias-row",
        title: "Bias",
        date: "2026-10-01",
        content: null,
        payload: { equity_bias: "neutral", notes: "Desk was split.", vix_level: 18.4, doc_type: "bias_row" },
      },
    ];
    const alt = documentsForStep(rows, "Research", "Alt-data", "2026-10-01");
    expect(alt.documents.map((doc) => doc.documentKey)).toEqual(["alt-cta-positioning", "alt-news"]);
    expect(alt.documents[0]?.fields).toEqual([{ key: "content", text: "Positioning was light." }]);
    expect(alt.documents[1]?.fields).toEqual([{ key: "body", text: "Headline from the payload." }]);
    expect(alt.withheldStub).toBe(false);

    const bias = documentsForStep(rows, "Synthesis", "Consolidate bias", "2026-10-01");
    expect(bias.documents[0]?.fields.map((field) => field.key)).toEqual(["equity_bias", "notes"]);
    expect(bias.documents[0]?.fields.map((field) => field.text).join(" ")).not.toContain("18.4");
  });

  it("withholds stub envelopes and leaves a missing text field empty", () => {
    const stub = documentsForStep(
      [{ document_key: "inputs", title: "Inputs", date: "2026-10-01", content: "legacy_estimate nav 99.909", payload: null }],
      "Inputs",
      "Preflight / market data",
      "2026-10-01",
    );
    expect(stub.documents).toEqual([]);
    expect(stub.withheldStub).toBe(true);

    const blank = documentsForStep(
      [{ document_key: "inputs", title: "Inputs", date: "2026-10-01", content: null, payload: { doc_type: "inputs" } }],
      "Inputs",
      "Preflight / market data",
      "2026-10-01",
    );
    expect(blank.documents[0]?.fields).toEqual([]);
    expect(blank.documents[0]?.title).toBe("Inputs");
  });
});

describe("loadStepOutput", () => {
  it("returns the API failure and no invented output when the read is withheld", async () => {
    const get: Get = async () => fail("The official API withheld this read (upstream_empty).");
    const read = await loadStepOutput(get, "Research", "Alt-data", "2026-10-01", new Map());
    expect(read.missing).toBe(true);
    expect(read.documents).toEqual([]);
    expect(read.reason).toContain("withheld");
    expect(read.reason).not.toContain("99.909");
    expect(JSON.stringify(read)).not.toContain("legacy_estimate");
  });

  it("loads content for the recorded date and says when the step has no row", async () => {
    const seen: Record<string, string>[] = [];
    const get: Get = async (_path, query) => {
      seen.push(query ?? {});
      return ok([
        { document_key: "bias-row", title: "Bias row", date: "2026-10-02", content: "Equity bias was neutral.", payload: null },
      ]);
    };
    const hit = await loadStepOutput(get, "Synthesis", "Consolidate bias", "2026-10-02", new Map());
    expect(seen[0]?.select).toContain("content");
    expect(seen[0]?.select).toContain("payload");
    expect(seen[0]?.["eq.date"]).toBe("2026-10-02");
    expect(hit.missing).toBe(false);
    expect(hit.documents[0]?.fields[0]?.text).toBe("Equity bias was neutral.");

    const miss = await loadStepOutput(get, "Research", "Alt-data", "2026-10-02", new Map());
    expect(miss.missing).toBe(true);
    expect(miss.documents).toEqual([]);
    expect(miss.reason).toContain("No document for this step");
    expect(miss.reason).toContain("2026-10-02");
  });

  it("resolves the latest run date when the band has none", async () => {
    const get: Get = async (_path, query) => {
      if (query?.select === "document_key,title,run_type,date") {
        return ok([{ document_key: "macro", title: "Macro", date: "2026-10-03", run_type: "house" }]);
      }
      return ok([{ document_key: "macro", title: "Macro", date: "2026-10-03", content: "Growth is slowing.", payload: null }]);
    };
    const read = await loadStepOutput(get, "Research", "Macro", null, new Map());
    expect(read.runDate).toBe("2026-10-03");
    expect(read.documents[0]?.fields[0]?.text).toBe("Growth is slowing.");
  });
});

describe("StepOutputPanel", () => {
  it("paints an em dash and the honest reason when nothing came back", () => {
    const read: StepOutputRead = {
      runDate: null,
      documents: [],
      missing: true,
      reason: "The official API did not respond.",
    };
    const html = renderToStaticMarkup(<StepOutputPanel read={read} />);
    expect(html).toContain("—");
    expect(html).toContain("The official API did not respond.");
    expect(html).not.toContain("99.909");
    expect(html).not.toContain("204.04");
    expect(html).not.toContain("legacy_estimate");
  });
});
