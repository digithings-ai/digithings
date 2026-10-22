import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import { parseDigichatConfig } from "@/lib/deploy-config/schema";
import { SUPPORT_MATRIX, limitSupport } from "./matrix";
import { flattenLimits, limitsFromGuardrails } from "./schema";

const foundry = {
  type: "foundry" as const,
  projectEndpoint: "https://example.services.ai.azure.com/api/projects/p",
  agentName: "agent",
};

function deployment(backend: Record<string, unknown>, limits: unknown, extra: Record<string, unknown> = {}) {
  return parseDigichatConfig({
    version: 1,
    deployment: { slug: "x", backend, limits, ...extra },
  });
}

describe("limits schema", () => {
  it("leaves every shipped example with no limits and no guardrails", () => {
    const configDir = resolve(__dirname, "../../../config");
    const examples = resolve(configDir, "examples");
    const trials = readdirSync(configDir).filter((name) => name.endsWith("-trial-foundry.yaml"));
    expect(trials).toHaveLength(1);
    const trialName = trials[0];
    if (!trialName) throw new Error("foundry trial overlay missing");
    const files = [
      resolve(configDir, trialName),
      resolve(examples, "digithings-ai-embed.yaml"),
      resolve(examples, "occ-embed.yaml"),
    ];
    for (const file of files) {
      const cfg = parseDigichatConfig(loadYaml(readFileSync(file, "utf8")), file);
      const deployments = [cfg.deployment, ...Object.values(cfg.hosts ?? {})].filter(Boolean);
      for (const dep of deployments) {
        expect(dep?.limits).toBeUndefined();
        expect(dep?.guardrails).toBeUndefined();
      }
    }
  });

  it("accepts an empty limits block and enables nothing", () => {
    const cfg = deployment({ type: "digigraph" }, {});
    expect(flattenLimits(cfg.deployment?.limits)).toEqual([]);
  });

  it("parses each limit path on a house backend", () => {
    const cfg = deployment({ type: "digigraph" }, {
      combine: "all",
      tokens: {
        input: { perHour: { user: { max: 1000 } } },
        output: { perDay: { session: { max: 2000, onExceed: "block" } } },
        total: {
          perMinute: {
            deployment: { max: 80000, answerAt: 0.7, pauseAt: 0.9, onExceed: "pause" },
          },
        },
      },
      cost: {
        usd: { perDay: { user: { max: 0.08, onExceed: "fallback-auto" } } },
        prices: { "openai/gpt-6.1-sol": { inputPerM: 1.5, outputPerM: 7.77 } },
      },
      turns: { perSession: { session: { max: 12, onExceed: "block" } } },
      sessions: { perIp: { max: 1, window: "concurrent", onExceed: "block" } },
      toolCalls: { perTurn: { max: 5, onExceed: "pause" } },
      models: {
        standard: { maxOutputUsdPerMillion: 2 },
        premium: { manualOnly: true, onExceed: "fallback-auto" },
      },
    });
    const paths = flattenLimits(cfg.deployment?.limits).map((rule) => rule.path);
    expect(paths).toEqual([
      "limits.sessions.perIp",
      "limits.turns.perSession.session",
      "limits.models.premium",
      "limits.cost.usd.perDay.user",
      "limits.tokens.input.perHour.user",
      "limits.tokens.output.perDay.session",
      "limits.tokens.total.perMinute.deployment",
      "limits.toolCalls.perTurn",
    ]);
  });

  it("rejects a token fraction that cannot pause", () => {
    expect(() =>
      deployment({ type: "digigraph" }, {
        tokens: { total: { perMinute: { user: { max: 10, answerAt: 0.95, pauseAt: 0.9 } } } },
      }),
    ).toThrow(/answerAt must be below pauseAt/);
  });

  it("rejects a foundry cost budget and a per-user token budget", () => {
    expect(() =>
      deployment(foundry, { cost: { usd: { perDay: { user: { max: 1 } } } } }),
    ).toThrow(/not enforceable on the foundry backend/);
    expect(() =>
      deployment(foundry, {
        tokens: { total: { perMinute: { user: { max: 1000 } } } },
      }),
    ).toThrow(/limits\.tokens\.total\.perMinute\.user/);
  });

  it("accepts the foundry subset: deployment TPM, tool calls, turns, and sessions", () => {
    const cfg = deployment(foundry, {
      tokens: {
        total: { perMinute: { deployment: { max: 100000 }, subscription: { max: 100000 } } },
      },
      toolCalls: { perQuestion: { max: 5 } },
      turns: { perDay: { ip: { max: 20 } } },
      sessions: { perIp: { max: 1 } },
    });
    expect(flattenLimits(cfg.deployment?.limits).map((rule) => rule.path)).toEqual([
      "limits.sessions.perIp",
      "limits.turns.perDay.ip",
      "limits.tokens.total.perMinute.deployment",
      "limits.tokens.total.perMinute.subscription",
      "limits.toolCalls.perQuestion",
    ]);
  });

  it("warns and drops an unsupported foundry gate instead of ignoring it", () => {
    const cfg = deployment(foundry, {
      onUnsupported: "warn",
      cost: { usd: { perDay: { user: { max: 1 } } } },
      turns: { perSession: { session: { max: 4 } } },
    });
    expect(cfg.deployment?.limits?.cost).toBeUndefined();
    expect(cfg.deployment?.limits?.turns?.perSession?.session?.max).toBe(4);
    expect(cfg.deployment?.limits?.warnings?.[0]).toMatch(/limits\.cost\.usd\.perDay\.user/);
  });

  it("rejects model tiers on AG-UI and tool calls on A2A", () => {
    expect(() =>
      deployment(
        { type: "ag-ui", url: "https://agent.example/agui" },
        { models: { standard: { maxOutputUsdPerMillion: 2 }, premium: { manualOnly: true } } },
      ),
    ).toThrow(/not enforceable on the ag-ui backend/);
    expect(() =>
      deployment(
        { type: "a2a", baseUrl: "https://agent.example/a2a" },
        { toolCalls: { perTurn: { max: 3 } } },
      ),
    ).toThrow(/not enforceable on the a2a backend/);
  });

  it("allows AG-UI turns and best-effort tool calls", () => {
    const cfg = deployment(
      { type: "ag-ui", url: "https://agent.example/agui" },
      { turns: { perHour: { ip: { max: 10 } } }, toolCalls: { perTurn: { max: 4 } } },
    );
    expect(flattenLimits(cfg.deployment?.limits)).toHaveLength(2);
  });

  it("requires the standard cap to match models.priceCapUsdPerMillion", () => {
    expect(() =>
      deployment(
        { type: "digigraph" },
        { models: { standard: { maxOutputUsdPerMillion: 2 }, premium: { manualOnly: true } } },
        { models: { priceCapUsdPerMillion: 3 } },
      ),
    ).toThrow(/must match models.priceCapUsdPerMillion/);
    const cfg = deployment(
      { type: "digigraph" },
      { models: { standard: { maxOutputUsdPerMillion: 2 }, premium: { manualOnly: true } } },
      { models: { priceCapUsdPerMillion: 2 } },
    );
    expect(cfg.deployment?.models.priceCapUsdPerMillion).toBe(2);
  });

  it("rejects premium manualOnly with no way to tell a premium model", () => {
    expect(() =>
      deployment({ type: "digigraph" }, { models: { premium: { manualOnly: true } } }),
    ).toThrow(/needs a standard output cap or premium ids/);
  });

  it("rejects a session pause and a tool-call model fallback", () => {
    expect(() =>
      deployment({ type: "digigraph" }, { sessions: { perIp: { max: 1, onExceed: "pause" } } }),
    ).toThrow(/cannot pause/);
    expect(() =>
      deployment({ type: "digigraph" }, { toolCalls: { perTurn: { max: 2, onExceed: "fallback-auto" } } }),
    ).toThrow(/cannot fall back/);
  });

  it("rejects disagreeing guardrails and limits", () => {
    expect(() =>
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "x",
          backend: { type: "digigraph" },
          guardrails: { maxToolCallsPerTurn: 4 },
          limits: { toolCalls: { perTurn: { max: 5 } } },
        },
      }),
    ).toThrow(/disagrees with guardrails/);
  });

  it("projects the guardrails alias onto the same paths", () => {
    const limits = limitsFromGuardrails({
      maxToolCallsPerTurn: 5,
      answerAt: 0.7,
      pauseAt: 0.9,
      tokensPerMinute: { deployment: 100000, user: 80000 },
    });
    expect(flattenLimits(limits).map((rule) => [rule.path, rule.max, rule.onExceed])).toEqual([
      ["limits.tokens.total.perMinute.deployment", 100000, "pause"],
      ["limits.tokens.total.perMinute.user", 80000, "pause"],
      ["limits.toolCalls.perTurn", 5, "pause"],
    ]);
  });

  it("accepts the model-picker cost budget as one premium gate", () => {
    const cfg = deployment(
      { type: "digigraph" },
      { models: { standard: { maxOutputUsdPerMillion: 2 }, premium: { manualOnly: true } } },
      {
        models: {
          priceCapUsdPerMillion: 2,
          premiumCapUsdPerMillion: 2.5,
          costPerWindow: { usd: 0.0125565, windowSeconds: 86400 },
        },
      },
    );
    expect(cfg.deployment?.models.costPerWindow).toEqual({ usd: 0.0125565, windowSeconds: 86400 });
  });

  it("rejects a foundry premium budget and a disagreeing cost gate", () => {
    expect(() =>
      deployment(foundry, undefined, {
        models: { priceCapUsdPerMillion: 2, costPerWindow: { usd: 0.01 } },
      }),
    ).toThrow(/models\.costPerWindow is not enforceable on the foundry backend/);
    expect(() =>
      deployment(
        { type: "digigraph" },
        { cost: { usd: { perDay: { user: { max: 1, premiumOnly: true } } } } },
        { models: { priceCapUsdPerMillion: 2, costPerWindow: { usd: 0.01, windowSeconds: 86400 } } },
      ),
    ).toThrow(/disagrees with limits\.cost\.usd\.perDay\.user/);
  });

  it("drops a foundry premium budget when unsupported gates warn", () => {
    const cfg = deployment(
      foundry,
      { onUnsupported: "warn" },
      { models: { priceCapUsdPerMillion: 2, costPerWindow: { usd: 0.01, windowSeconds: 86400 } } },
    );
    expect(cfg.deployment?.models.costPerWindow).toBeUndefined();
    expect(cfg.deployment?.models.priceCapUsdPerMillion).toBe(2);
  });

  it("pins the backend matrix", () => {
    expect(SUPPORT_MATRIX.digigraph.models).toBe("enforce");
    expect(SUPPORT_MATRIX.digigraph.toolCalls).toBe("best-effort");
    expect(SUPPORT_MATRIX.langgraph.tokens).toBe("best-effort");
    expect(SUPPORT_MATRIX.foundry.cost).toBe("unsupported");
    expect(SUPPORT_MATRIX.foundry.tokens).toBe("partial");
    expect(SUPPORT_MATRIX["ag-ui"].tokens).toBe("unsupported");
    expect(SUPPORT_MATRIX["ag-ui"].toolCalls).toBe("best-effort");
    expect(SUPPORT_MATRIX.a2a.toolCalls).toBe("unsupported");
    expect(SUPPORT_MATRIX.a2a.sessions).toBe("enforce");
    expect(limitSupport("foundry", { kind: "tokens", metric: "total", scope: "deployment", window: "minute" })).toBe(
      "enforce",
    );
    expect(limitSupport("foundry", { kind: "tokens", metric: "input", scope: "deployment", window: "minute" })).toBe(
      "unsupported",
    );
    expect(limitSupport("foundry", { kind: "turns" })).toBe("enforce");
    expect(limitSupport("openai-completions", { kind: "cost" })).toBe("enforce");
  });
});
