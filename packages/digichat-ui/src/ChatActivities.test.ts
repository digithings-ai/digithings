import { describe, it, expect } from "vitest";
import type { DigiChatActivity, VaultHitSummary } from "./types";

function assertNever(x: never): never {
  throw new Error(`unexpected: ${JSON.stringify(x)}`);
}

function kindLabel(a: DigiChatActivity): string {
  switch (a.kind) {
    case "status":
    case "tool_call":
    case "tool_result":
    case "reasoning":
    case "trace":
      return a.kind;
    case "brief":
      return "brief";
    default:
      return assertNever(a);
  }
}

describe("VaultHitSummary / DigiChatActivity Phase 2 shapes", () => {
  it("allows optional tier, year, snippet on hits", () => {
    const hit: VaultHitSummary = {
      title: "Auth",
      path: "docs/auth.md",
      tier: "peer_reviewed",
      year: 2024,
      snippet: "JWT exchange…",
    };
    expect(hit.tier).toBe("peer_reviewed");
    expect(hit.year).toBe(2024);
    expect(hit.snippet).toBe("JWT exchange…");
  });

  it("allows brief activity kind", () => {
    const row: DigiChatActivity = {
      kind: "brief",
      themes: [{ label: "Auth", summary: "RS256 tokens" }],
      questions: ["Which tenant?"],
    };
    expect(row.kind).toBe("brief");
    expect(row.themes).toHaveLength(1);
    expect(row.questions?.[0]).toBe("Which tenant?");
  });

  it("keeps thin {title,path} hits assignable", () => {
    const hit: VaultHitSummary = { title: "A", path: "p" };
    expect(hit).toEqual({ title: "A", path: "p" });
  });

  it("exhaustively handles brief", () => {
    expect(
      kindLabel({
        kind: "brief",
        themes: [{ label: "T", summary: "S" }],
      }),
    ).toBe("brief");
  });
});
