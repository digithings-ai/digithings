/**
 * Canonical digichat limits. Omit `limits` and every gate is off.
 *
 * `guardrails` from the shared token and tool-call block is the alias of
 * `limits.tokens.total.perMinute` plus `limits.toolCalls.perTurn`. New
 * configs should use `limits`. A deployment that sets both must not disagree.
 *
 * Gates combine with AND. Evaluation walks them in a fixed order and the
 * first one that is already exceeded wins. See `evaluate.ts`.
 */

import { z } from "zod";
import { limitSupport, type LimitKind, type Support } from "./matrix";

export const ON_EXCEED = ["block", "fallback-auto", "pause"] as const;
export type OnExceed = (typeof ON_EXCEED)[number];

const OnExceedSchema = z.enum(ON_EXCEED);
const Fraction = z.number().gt(0).max(1);
const Message = z.string().min(1).max(400);
const Count = z.number().int().positive().max(10_000_000);
const Usd = z.number().positive().max(1_000_000);

const PlainGate = z
  .object({
    max: z.number().positive(),
    onExceed: OnExceedSchema.optional(),
    message: Message.optional(),
  })
  .strict();

const CountGate = PlainGate.extend({ max: Count });
const UsdGate = PlainGate.extend({
  max: Usd,
  /** When true, only a premium model spends this budget. */
  premiumOnly: z.boolean().optional(),
});

const TokenGate = CountGate.extend({
  answerAt: Fraction.optional(),
  pauseAt: Fraction.optional(),
}).superRefine((value, ctx) => {
  const answer = value.answerAt ?? 0.7;
  const pause = value.pauseAt ?? 0.9;
  if (value.answerAt != null || value.pauseAt != null) {
    if (answer >= pause) {
      ctx.addIssue({
        code: "custom",
        message: "answerAt must be below pauseAt",
        path: ["answerAt"],
      });
    }
  }
});

const SCOPES = ["deployment", "subscription", "user", "ip", "session"] as const;
export type LimitScope = (typeof SCOPES)[number];

function scopeMap<T extends z.ZodType>(gate: T) {
  return z
    .object({
      deployment: gate.optional(),
      subscription: gate.optional(),
      user: gate.optional(),
      ip: gate.optional(),
      session: gate.optional(),
    })
    .strict();
}

function windowMap<T extends z.ZodType>(gate: T) {
  const scopes = scopeMap(gate);
  return z
    .object({
      perMinute: scopes.optional(),
      perHour: scopes.optional(),
      perDay: scopes.optional(),
      perSession: scopes.optional(),
    })
    .strict();
}

const TokenWindows = windowMap(TokenGate);
const CountWindows = windowMap(CountGate);
const UsdWindows = windowMap(UsdGate);

const Price = z
  .object({
    inputPerM: z.number().nonnegative(),
    outputPerM: z.number().nonnegative(),
  })
  .strict();

export const LimitsSchema = z
  .object({
    /** Every gate must pass. The only combination. */
    combine: z.literal("all").optional(),
    /**
     * What to do with a gate this backend cannot enforce.
     * `reject` (default) fails config load. `warn` drops the gate and records
     * `warnings` so it is not a silent skip.
     */
    onUnsupported: z.enum(["reject", "warn"]).optional(),
    tokens: z
      .object({
        input: TokenWindows.optional(),
        output: TokenWindows.optional(),
        total: TokenWindows.optional(),
      })
      .strict()
      .optional(),
    cost: z
      .object({
        usd: UsdWindows.optional(),
        /** USD per million tokens. Wins over the model catalog for that id. */
        prices: z.record(z.string().min(1), Price).optional(),
      })
      .strict()
      .optional(),
    turns: CountWindows.optional(),
    sessions: z
      .object({
        perIp: z
          .object({
            max: Count,
            window: z.enum(["minute", "hour", "day", "concurrent"]).optional(),
            /** How long a live chat still occupies a concurrent slot. Default 30. */
            idleMinutes: z.number().positive().max(24 * 60).optional(),
            onExceed: OnExceedSchema.optional(),
            message: Message.optional(),
          })
          .strict(),
      })
      .strict()
      .optional(),
    toolCalls: z
      .object({
        perTurn: CountGate.optional(),
        /** Same gate as perTurn. Set only one. */
        perQuestion: CountGate.optional(),
      })
      .strict()
      .optional(),
    models: z
      .object({
        standard: z
          .object({
            /** Same number as `models.priceCapUsdPerMillion` when both are set. */
            maxOutputUsdPerMillion: z.number().positive(),
          })
          .strict()
          .optional(),
        premium: z
          .object({
            manualOnly: z.boolean(),
            /** Ids treated as premium even when no price is loaded. */
            ids: z.array(z.string().min(1)).optional(),
            onExceed: OnExceedSchema.optional(),
            message: Message.optional(),
          })
          .strict()
          .optional(),
      })
      .strict()
      .optional(),
    /** Filled by validation when `onUnsupported` is `warn`. Not a YAML input. */
    warnings: z.array(z.string()).optional(),
  })
  .strict();

export type LimitsConfig = z.infer<typeof LimitsSchema>;

export type LimitWindow = "minute" | "hour" | "day" | "session" | "turn" | "concurrent";

export type LimitRule = {
  path: string;
  kind: LimitKind;
  metric?: "input" | "output" | "total";
  scope: LimitScope;
  window: LimitWindow;
  max?: number;
  onExceed: OnExceed;
  message?: string;
  answerAt?: number;
  pauseAt?: number;
  manualOnly?: boolean;
  premiumOnly?: boolean;
  premiumIds?: readonly string[];
  maxOutputUsdPerMillion?: number;
  idleMinutes?: number;
  /** Set when the gate is a rolling `models.costPerWindow`, including a custom length. */
  windowMs?: number;
};

type GateFields = {
  max: number;
  onExceed?: OnExceed;
  message?: string;
  answerAt?: number;
  pauseAt?: number;
  premiumOnly?: boolean;
};

const WINDOW_KEYS = [
  ["perMinute", "minute"],
  ["perHour", "hour"],
  ["perDay", "day"],
  ["perSession", "session"],
] as const;

function defaultOnExceed(kind: LimitKind): OnExceed {
  if (kind === "tokens" || kind === "toolCalls") return "pause";
  if (kind === "models") return "fallback-auto";
  return "block";
}

function pushGate(
  rules: LimitRule[],
  base: Omit<LimitRule, "onExceed" | "max"> & { onExceed?: OnExceed },
  gate: GateFields,
): void {
  rules.push({
    ...base,
    max: gate.max,
    onExceed: gate.onExceed ?? base.onExceed ?? defaultOnExceed(base.kind),
    ...(gate.message ? { message: gate.message } : {}),
    ...(gate.answerAt != null ? { answerAt: gate.answerAt } : {}),
    ...(gate.pauseAt != null ? { pauseAt: gate.pauseAt } : {}),
    ...(gate.premiumOnly ? { premiumOnly: true } : {}),
  });
}

function walkWindows(
  rules: LimitRule[],
  path: string,
  kind: LimitKind,
  windows: Record<string, Record<string, GateFields> | undefined> | undefined,
  metric?: LimitRule["metric"],
): void {
  if (!windows) return;
  for (const [key, window] of WINDOW_KEYS) {
    const scopes = windows[key];
    if (!scopes) continue;
    for (const scope of SCOPES) {
      const gate = scopes[scope];
      if (!gate) continue;
      pushGate(
        rules,
        {
          path: `${path}.${key}.${scope}`,
          kind,
          ...(metric ? { metric } : {}),
          scope,
          window,
        },
        gate,
      );
    }
  }
}

/** Flat rules in evaluation order: sessions, turns, models, cost, tokens, tool calls. */
export function flattenLimits(limits: LimitsConfig | undefined | null): LimitRule[] {
  if (!limits) return [];
  const rules: LimitRule[] = [];

  const sessions = limits.sessions?.perIp;
  if (sessions) {
    rules.push({
      path: "limits.sessions.perIp",
      kind: "sessions",
      scope: "ip",
      window: sessions.window ?? "concurrent",
      max: sessions.max,
      onExceed: sessions.onExceed ?? "block",
      ...(sessions.message ? { message: sessions.message } : {}),
      ...(sessions.idleMinutes != null ? { idleMinutes: sessions.idleMinutes } : {}),
    });
  }

  walkWindows(rules, "limits.turns", "turns", limits.turns);

  const premium = limits.models?.premium;
  if (premium) {
    rules.push({
      path: "limits.models.premium",
      kind: "models",
      scope: "deployment",
      window: "session",
      onExceed: premium.onExceed ?? "fallback-auto",
      manualOnly: premium.manualOnly,
      ...(premium.ids ? { premiumIds: premium.ids } : {}),
      ...(limits.models?.standard
        ? { maxOutputUsdPerMillion: limits.models.standard.maxOutputUsdPerMillion }
        : {}),
      ...(premium.message ? { message: premium.message } : {}),
    });
  }

  walkWindows(rules, "limits.cost.usd", "cost", limits.cost?.usd);

  if (limits.tokens) {
    walkWindows(rules, "limits.tokens.input", "tokens", limits.tokens.input, "input");
    walkWindows(rules, "limits.tokens.output", "tokens", limits.tokens.output, "output");
    walkWindows(rules, "limits.tokens.total", "tokens", limits.tokens.total, "total");
  }

  const perTurn = limits.toolCalls?.perTurn;
  const perQuestion = limits.toolCalls?.perQuestion;
  const tool = perTurn ?? perQuestion;
  if (tool) {
    pushGate(
      rules,
      {
        path: perTurn ? "limits.toolCalls.perTurn" : "limits.toolCalls.perQuestion",
        kind: "toolCalls",
        scope: "session",
        window: "turn",
      },
      tool,
    );
  }

  return rules;
}

export type LimitIssue = { path: (string | number)[]; message: string };

function pathOf(rulePath: string): (string | number)[] {
  return rulePath.split(".");
}

/**
 * Structural problems, and unsupported gates when the policy is reject.
 * Warn-mode drops happen in `applyUnsupportedPolicy`, not here.
 */
export function collectLimitIssues(
  limits: LimitsConfig | undefined,
  backendType: string,
  priceCapUsdPerMillion?: number,
): LimitIssue[] {
  if (!limits) return [];
  const issues: LimitIssue[] = [];
  if (limits.warnings?.length) {
    issues.push({
      path: ["limits", "warnings"],
      message: "limits.warnings is written by validation, not by the config file",
    });
  }
  const perTurn = limits.toolCalls?.perTurn;
  const perQuestion = limits.toolCalls?.perQuestion;
  if (perTurn && perQuestion && perTurn.max !== perQuestion.max) {
    issues.push({
      path: ["limits", "toolCalls", "perQuestion"],
      message: "limits.toolCalls.perQuestion must match limits.toolCalls.perTurn",
    });
  }
  const standard = limits.models?.standard?.maxOutputUsdPerMillion;
  if (
    limits.models?.premium?.manualOnly &&
    standard == null &&
    priceCapUsdPerMillion == null &&
    !limits.models.premium.ids?.length
  ) {
    issues.push({
      path: ["limits", "models", "premium"],
      message: "limits.models.premium.manualOnly needs a standard output cap or premium ids",
    });
  }
  if (standard != null && priceCapUsdPerMillion != null && standard !== priceCapUsdPerMillion) {
    issues.push({
      path: ["limits", "models", "standard", "maxOutputUsdPerMillion"],
      message:
        "limits.models.standard.maxOutputUsdPerMillion must match models.priceCapUsdPerMillion",
    });
  }
  const premiumIds = limits.models?.premium?.ids;
  if (
    flattenLimits(limits).some((rule) => rule.kind === "cost" && rule.premiumOnly) &&
    standard == null &&
    priceCapUsdPerMillion == null &&
    !premiumIds?.length
  ) {
    issues.push({
      path: ["limits", "cost"],
      message: "limits.cost premiumOnly needs a standard output cap or premium ids",
    });
  }
  const mode = limits.onUnsupported ?? "reject";
  for (const rule of flattenLimits(limits)) {
    if (rule.kind === "toolCalls" && rule.onExceed === "fallback-auto") {
      issues.push({
        path: pathOf(rule.path).concat("onExceed"),
        message: "tool-call limits cannot fall back to another model",
      });
    }
    if (rule.kind === "sessions" && rule.onExceed === "pause") {
      issues.push({
        path: pathOf(rule.path).concat("onExceed"),
        message: "a session limit cannot pause and summarize a chat that has not started",
      });
    }
    if (mode === "warn") continue;
    const support: Support = limitSupport(backendType, rule);
    if (support === "unsupported") {
      issues.push({
        path: pathOf(rule.path),
        message: `${rule.path} is not enforceable on the ${backendType} backend`,
      });
    }
  }
  return issues;
}

type Json = Record<string, unknown>;

function asRecord(value: unknown): Json | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  return value as Json;
}

function deletePath(root: Json, parts: string[]): void {
  const walk = (node: Json, index: number) => {
    const key = parts[index];
    if (!key) return;
    if (index === parts.length - 1) {
      delete node[key];
      return;
    }
    const child = asRecord(node[key]);
    if (!child) return;
    walk(child, index + 1);
    if (Object.keys(child).length === 0) delete node[key];
  };
  walk(root, 0);
}

/**
 * Drop unsupported gates and record a warning for each one.
 * Prices, the standard cap, and `onUnsupported` stay.
 */
export function applyUnsupportedPolicy(
  limits: LimitsConfig,
  backendType: string,
): { limits: LimitsConfig; warnings: string[] } {
  const warnings: string[] = [];
  const clone = structuredClone(limits) as LimitsConfig & Json;
  delete clone.warnings;
  for (const rule of flattenLimits(limits)) {
    if (limitSupport(backendType, rule) !== "unsupported") continue;
    warnings.push(`${rule.path} is not enforceable on the ${backendType} backend and was dropped`);
    deletePath(clone, rule.path.split(".").slice(1));
  }
  if (warnings.length) clone.warnings = warnings;
  return { limits: clone, warnings };
}

/** The subset the existing turn guard already enforces (pause, not block). */
export type GuardrailAlias = {
  maxToolCallsPerTurn?: number;
  answerAt?: number;
  pauseAt?: number;
  tokensPerMinute?: { deployment?: number; user?: number };
};

export function limitsFromGuardrails(guardrails: GuardrailAlias | undefined | null): LimitsConfig | undefined {
  if (!guardrails) return undefined;
  const tool = guardrails.maxToolCallsPerTurn;
  const deployment = guardrails.tokensPerMinute?.deployment;
  const user = guardrails.tokensPerMinute?.user;
  if (tool == null && deployment == null && user == null && guardrails.answerAt == null && guardrails.pauseAt == null) {
    return undefined;
  }
  const fractions = {
    ...(guardrails.answerAt != null ? { answerAt: guardrails.answerAt } : {}),
    ...(guardrails.pauseAt != null ? { pauseAt: guardrails.pauseAt } : {}),
  };
  const limits: LimitsConfig = {};
  if (tool != null) {
    limits.toolCalls = { perTurn: { max: tool, onExceed: "pause" } };
  }
  if (deployment != null || user != null) {
    limits.tokens = {
      total: {
        perMinute: {
          ...(deployment != null
            ? { deployment: { max: deployment, onExceed: "pause" as const, ...fractions } }
            : {}),
          ...(user != null ? { user: { max: user, onExceed: "pause" as const, ...fractions } } : {}),
        },
      },
    };
  }
  return limits;
}

/**
 * Project pause-style token and tool gates back onto the turn guard.
 * Block and fallback gates stay in the pre-turn check and are not copied.
 */
export function guardrailsFromLimits(limits: LimitsConfig | undefined | null): GuardrailAlias | undefined {
  if (!limits) return undefined;
  const alias: GuardrailAlias = {};
  const tool = limits.toolCalls?.perTurn ?? limits.toolCalls?.perQuestion;
  if (tool && (tool.onExceed ?? "pause") === "pause") alias.maxToolCallsPerTurn = tool.max;
  const minute = limits.tokens?.total?.perMinute;
  let answerAt: number | undefined;
  let pauseAt: number | undefined;
  const take = (gate: { max: number; onExceed?: OnExceed; answerAt?: number; pauseAt?: number } | undefined) => {
    if (!gate || (gate.onExceed ?? "pause") !== "pause") return undefined;
    if (gate.answerAt != null) answerAt = gate.answerAt;
    if (gate.pauseAt != null) pauseAt = gate.pauseAt;
    return gate.max;
  };
  const deployment = take(minute?.deployment) ?? take(minute?.subscription);
  const user = take(minute?.user);
  if (deployment != null || user != null) {
    alias.tokensPerMinute = {
      ...(deployment != null ? { deployment } : {}),
      ...(user != null ? { user } : {}),
    };
  }
  if (answerAt != null) alias.answerAt = answerAt;
  if (pauseAt != null) alias.pauseAt = pauseAt;
  if (!alias.maxToolCallsPerTurn && !alias.tokensPerMinute) return undefined;
  return alias;
}

export function limitsDisagree(alias: GuardrailAlias, limits: LimitsConfig): string | null {
  const projected = limitsFromGuardrails(alias);
  if (!projected) return null;
  const fromAlias = flattenLimits(projected);
  const fromLimits = flattenLimits(limits);
  for (const rule of fromAlias) {
    const other = fromLimits.find((candidate) => candidate.path === rule.path);
    if (!other) continue;
    if (other.max !== rule.max) {
      return `${rule.path} disagrees with guardrails (${other.max} and ${rule.max})`;
    }
  }
  return null;
}

/** #6193 spelling of a per-user premium cost gate. */
export const CostPerWindowSchema = z
  .object({
    usd: z.number().positive(),
    windowSeconds: z.number().int().positive().default(86_400),
  })
  .strict();

export type CostPerWindow = z.infer<typeof CostPerWindowSchema>;

const PREMIUM_BUDGET_MESSAGE =
  "You've used today's premium budget. Answering with Auto instead.";

export function namedWindow(windowSeconds: number): LimitWindow | undefined {
  if (windowSeconds === 60) return "minute";
  if (windowSeconds === 3_600) return "hour";
  if (windowSeconds === 86_400) return "day";
  return undefined;
}

export function ruleFromCostPerWindow(
  budget: CostPerWindow,
  caps: { outputCapUsdPerMillion?: number; premiumIds?: readonly string[] },
): LimitRule {
  const named = namedWindow(budget.windowSeconds);
  return {
    path: "models.costPerWindow",
    kind: "cost",
    scope: "user",
    window: named ?? "day",
    windowMs: budget.windowSeconds * 1000,
    max: budget.usd,
    onExceed: "fallback-auto",
    premiumOnly: true,
    message: PREMIUM_BUDGET_MESSAGE,
    ...(caps.outputCapUsdPerMillion != null
      ? { maxOutputUsdPerMillion: caps.outputCapUsdPerMillion }
      : {}),
    ...(caps.premiumIds?.length ? { premiumIds: caps.premiumIds } : {}),
  };
}

export function costPerWindowCovered(
  limits: LimitsConfig | undefined | null,
  budget: CostPerWindow,
): boolean {
  const named = namedWindow(budget.windowSeconds);
  if (!named || !limits) return false;
  return flattenLimits(limits).some(
    (rule) =>
      rule.kind === "cost" &&
      rule.scope === "user" &&
      rule.window === named &&
      rule.max === budget.usd &&
      rule.premiumOnly === true,
  );
}

/** Null when the alias can stand beside `limits`, or there is no `limits` cost gate. */
export function costPerWindowIssue(
  limits: LimitsConfig | undefined | null,
  budget: CostPerWindow,
): string | null {
  const named = namedWindow(budget.windowSeconds);
  if (!named || !limits) return null;
  const rule = flattenLimits(limits).find(
    (candidate) =>
      candidate.kind === "cost" && candidate.scope === "user" && candidate.window === named,
  );
  if (!rule) return null;
  if (rule.max !== budget.usd) {
    return `models.costPerWindow.usd disagrees with ${rule.path} (${budget.usd} and ${rule.max})`;
  }
  if (!rule.premiumOnly) {
    return `models.costPerWindow meters premium models only; ${rule.path} must set premiumOnly: true`;
  }
  return null;
}

/** Resolved standard-tier output cap. Either YAML path. They must match when both are set. */
export function standardOutputCap(
  limits: LimitsConfig | undefined | null,
  priceCapUsdPerMillion?: number,
): number | undefined {
  return limits?.models?.standard?.maxOutputUsdPerMillion ?? priceCapUsdPerMillion;
}
