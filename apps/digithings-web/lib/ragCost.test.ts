import { describe, it, expect } from "vitest";
import {
  DEFAULT_WORKLOAD,
  RAG_PRICING,
  TOKENS_PER_GB,
  ragCost,
  scaleWorkload,
} from "@/lib/ragCost";

describe("ragCost", () => {
  it("sizes the corpus at 250M tokens per GB in 500-token chunks", () => {
    expect(TOKENS_PER_GB).toBe(250_000_000);
    expect((DEFAULT_WORKLOAD.corpusGB * TOKENS_PER_GB) / DEFAULT_WORKLOAD.chunkTokens).toBe(500_000);
  });

  it("prices the provider setup as one-time embeddings plus index writes", () => {
    // 250M tokens x $0.13/M = $32.50, plus 500k writes x $4/M = $2.00.
    const { setup } = ragCost("provider");
    expect(setup).toBeCloseTo(34.5, 6);
  });

  it("prices the provider month with chat dominating store, queries and traces", () => {
    // Store 6.144GB x $0.33 = $2.03, reads 30k x 6.144 RU x $16/M = $2.95:
    // under the $50 floor, so $50. Query embeddings 60M x $0.13 = $7.80.
    // Sol answers 240M x $4 + 45M x $20 = $1,860. LangSmith $39 + 20k x
    // $2.50/1k = $89. Total $2,006.80.
    const { monthly, lines } = ragCost("provider");
    expect(monthly).toBeCloseTo(2006.8, 4);
    const answers = lines.find((l) => l.label === "Model answers");
    expect(answers!.amount / monthly).toBeGreaterThan(0.9);
  });

  it("runs self-hosted at zero marginal dollars", () => {
    const { setup, monthly } = ragCost("dg-self");
    expect(setup).toBe(0);
    expect(monthly).toBe(0);
  });

  it("prices cheap-managed an order of magnitude under provider", () => {
    // $25 store + 60M x $0.02 query embeddings + Luna 240M x $0.20 +
    // 45M x $1.20 answers = $128.20/mo; $5 setup.
    const { setup, monthly } = ragCost("dg-cheap");
    expect(setup).toBeCloseTo(5, 6);
    expect(monthly).toBeCloseTo(128.2, 4);
    expect(ragCost("provider").monthly / monthly).toBeGreaterThan(10);
  });

  it("keeps flagship-routed below provider by exactly the traces bill", () => {
    const provider = ragCost("provider");
    const flagship = ragCost("dg-flagship");
    expect(flagship.setup).toBeCloseTo(provider.setup, 6);
    expect(provider.monthly - flagship.monthly).toBeCloseTo(89, 4);
  });

  it("explodes with scale — the 10x month is ~10x, led by answers", () => {
    const base = ragCost("provider").monthly;
    const scaled = ragCost("provider", scaleWorkload(DEFAULT_WORKLOAD, 10)).monthly;
    expect(scaled / base).toBeGreaterThan(9);
    expect(scaled / base).toBeLessThan(11);
  });

  it("scales corpus and queries together", () => {
    const scaled = scaleWorkload(DEFAULT_WORKLOAD, 3);
    expect(scaled.corpusGB).toBe(3);
    expect(scaled.queriesPerDay).toBe(3000);
    expect(RAG_PRICING.researchedAt).toBe("2026-09-28");
  });
});
