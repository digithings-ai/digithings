/**
 * In-process port of `digillm.router`.
 *
 * Python is the source of truth. This file scores the same way, and it reads
 * the same `router_data.json` (phrases, rules, prices). The bundler inlines
 * that JSON, so the stock image and the Cloudflare Worker do not need Python
 * or a filesystem read. `DIGILLM_ROUTER_PYTHON=1` is the only path that
 * spawns the Python process instead.
 */

import routerData from "../../../../digillm/src/digillm/router/router_data.json";

import {
  type DigillmRouterDecision,
  type DigillmRouterRouteInput,
} from "@/lib/digillm-router";
import { premiumModelIds, resolveDigillmPresets } from "@/lib/digillm-router-catalog";

const FNV_OFFSET = 2166136261;
const FNV_PRIME = 16777619;
const encoder = new TextEncoder();

type RuleOp = "match" | "search" | "search_or_long";

type RouterRule = {
  id: string;
  route: string;
  op: RuleOp;
  pattern: string;
  flags: string;
  reason: string;
  confidence: number;
  max_chars?: number;
  unless_pattern?: string;
  unless_flags?: string;
  numbered_pattern?: string;
  numbered_flags?: string;
  long_chars?: number;
};

type TableRoute = {
  id: string;
  label: string;
  description: string;
  exemplars: string[];
};

type RouterTable = {
  dim: number;
  weak: number;
  stopwords: string[];
  token_pattern: string;
  bind: string;
  rules: RouterRule[];
  routes: TableRoute[];
};

export class DigillmRouterEngineError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DigillmRouterEngineError";
  }
}

type CompiledRule = {
  route: string;
  op: RuleOp;
  regex: RegExp;
  reason: string;
  confidence: number;
  maxChars: number | undefined;
  unless: RegExp | undefined;
  numbered: RegExp | undefined;
  longChars: number | undefined;
};

type WorkingRoute = {
  id: string;
  label: string;
  description: string;
  model?: string;
  exemplars: string[];
};

function isRuleOp(value: string): value is RuleOp {
  return value === "match" || value === "search" || value === "search_or_long";
}

function flagsToRegExp(pattern: string, flags: string): RegExp {
  let spec = "";
  if (flags.includes("i")) spec += "i";
  if (flags.includes("m")) spec += "m";
  return new RegExp(pattern, spec);
}

function loadTable(raw: RouterTable): {
  dim: number;
  weak: number;
  stop: Set<string>;
  token: RegExp;
  rules: CompiledRule[];
  routes: WorkingRoute[];
} {
  if (raw.bind !== "catalog_presets") {
    throw new DigillmRouterEngineError("router_data.json bind is not catalog_presets");
  }
  const rules: CompiledRule[] = raw.rules.map((rule) => {
    if (!isRuleOp(rule.op)) {
      throw new DigillmRouterEngineError("router_data.json has an unknown rule op");
    }
    return {
      route: rule.route,
      op: rule.op,
      regex: flagsToRegExp(rule.pattern, rule.flags ?? ""),
      reason: rule.reason,
      confidence: rule.confidence,
      maxChars: rule.max_chars,
      unless: rule.unless_pattern
        ? flagsToRegExp(rule.unless_pattern, rule.unless_flags ?? "")
        : undefined,
      numbered: rule.numbered_pattern
        ? flagsToRegExp(rule.numbered_pattern, rule.numbered_flags ?? "")
        : undefined,
      longChars: rule.long_chars,
    };
  });
  const routes: WorkingRoute[] = raw.routes.map((route) => ({
    id: route.id,
    label: route.label,
    description: route.description,
    exemplars: [...route.exemplars],
  }));
  return {
    dim: raw.dim,
    weak: raw.weak,
    stop: new Set(raw.stopwords),
    token: flagsToRegExp(raw.token_pattern, "i"),
    rules,
    routes,
  };
}

const TABLE = loadTable(routerData as RouterTable);
const PRESETS = resolveDigillmPresets();

function cleanAllow(allowed: readonly string[]): string[] {
  return allowed.map((item) => item.trim()).filter((item) => item.length > 0);
}

function presetModel(routeId: string): string {
  if (routeId === "reasoning") return PRESETS.reasoning;
  if (routeId === "fast") return PRESETS.fast;
  if (routeId === "light") return PRESETS.light;
  return "";
}

function onAllowList(modelId: string, allowSet: ReadonlySet<string>): boolean {
  return modelId.length > 0 && (allowSet.size === 0 || allowSet.has(modelId));
}

function bindModel(route: WorkingRoute, allow: readonly string[], fallback: string): string {
  const allowSet = new Set(allow);
  const pinned = route.model?.trim() ?? "";
  if (pinned) {
    if (premiumModelIds().has(pinned)) {
      throw new DigillmRouterEngineError(`router will not use premium model ${pinned}`);
    }
    if (allowSet.size > 0 && !allowSet.has(pinned)) {
      throw new DigillmRouterEngineError(
        `router route ${route.id} pins ${pinned}, which is not on the allowlist`,
      );
    }
    return pinned;
  }
  const preset = presetModel(route.id).trim();
  if (onAllowList(preset, allowSet)) return preset;
  const auto = PRESETS.auto.trim();
  if (onAllowList(auto, allowSet)) return auto;
  const fallbackId = fallback.trim();
  if (onAllowList(fallbackId, allowSet)) return fallbackId;
  if (allow.length > 0 && allow[0]) return allow[0];
  throw new DigillmRouterEngineError("router has no model to choose");
}

function resolveRoutes(overrides: readonly DigillmRouterRouteInput[] | undefined): WorkingRoute[] {
  const builtins = TABLE.routes.map((route) => ({ ...route, exemplars: [...route.exemplars] }));
  if (!overrides || overrides.length === 0) return builtins;
  const byId = new Map(builtins.map((route) => [route.id, route]));
  const order = builtins.map((route) => route.id);
  const extras: WorkingRoute[] = [];
  const seen = new Set<string>();
  for (const override of overrides) {
    if (seen.has(override.id)) {
      throw new DigillmRouterEngineError(`duplicate router route ${override.id}`);
    }
    seen.add(override.id);
    const current = byId.get(override.id);
    if (!current) {
      extras.push({
        id: override.id,
        label: override.label,
        description: override.description,
        model: override.model,
        exemplars: override.exemplars ? [...override.exemplars] : [],
      });
      continue;
    }
    current.label = override.label;
    current.description = override.description;
    if (override.model) current.model = override.model;
    if (override.exemplars && override.exemplars.length > 0) {
      current.exemplars = [...override.exemplars];
    }
  }
  const ordered: WorkingRoute[] = [];
  for (const id of order) {
    const route = byId.get(id);
    if (route) ordered.push(route);
  }
  return [...ordered, ...extras];
}

function tokens(text: string): string[] {
  const found = text.match(new RegExp(TABLE.token.source, "gi")) ?? [];
  return found.map((token) => token.toLowerCase()).filter((token) => !TABLE.stop.has(token));
}

function hashToken(token: string): [number, number] {
  let hashed = FNV_OFFSET;
  for (const byte of encoder.encode(token)) {
    hashed = (hashed ^ byte) >>> 0;
    hashed = Math.imul(hashed, FNV_PRIME) >>> 0;
  }
  const index = hashed % TABLE.dim;
  const sign = (hashed >>> 8) & 1 ? 1 : -1;
  return [index, sign];
}

function vector(text: string): number[] {
  const vec = Array.from({ length: TABLE.dim }, () => 0);
  for (const token of tokens(text)) {
    const [index, sign] = hashToken(token);
    vec[index] = (vec[index] ?? 0) + sign;
  }
  const norm = Math.sqrt(vec.reduce((sum, value) => sum + value * value, 0));
  if (norm === 0) return vec;
  return vec.map((value) => value / norm);
}

function exemplarTexts(route: WorkingRoute): string[] {
  return [route.description, ...route.exemplars].map((text) => text.trim()).filter(Boolean);
}

function centroid(route: WorkingRoute): number[] {
  const texts = exemplarTexts(route);
  if (texts.length === 0) return Array.from({ length: TABLE.dim }, () => 0);
  const acc = Array.from({ length: TABLE.dim }, () => 0);
  for (const text of texts) {
    vector(text).forEach((value, index) => {
      acc[index] = (acc[index] ?? 0) + value;
    });
  }
  const norm = Math.sqrt(acc.reduce((sum, value) => sum + value * value, 0));
  if (norm === 0) return acc;
  return acc.map((value) => value / norm);
}

function cosine(left: readonly number[], right: readonly number[]): number {
  let sum = 0;
  for (let index = 0; index < left.length; index += 1) {
    sum += (left[index] ?? 0) * (right[index] ?? 0);
  }
  return sum;
}

function hasRoute(routes: readonly WorkingRoute[], routeId: string): boolean {
  return routes.some((route) => route.id === routeId);
}

function ruleRoute(
  text: string,
  routes: readonly WorkingRoute[],
): { routeId: string; reason: string; confidence: number } | undefined {
  const stripped = text.trim();
  if (!stripped) return undefined;
  for (const rule of TABLE.rules) {
    if (!hasRoute(routes, rule.route)) continue;
    if (rule.maxChars !== undefined && stripped.length >= rule.maxChars) continue;
    switch (rule.op) {
      case "match":
        if (rule.regex.test(stripped)) {
          return { routeId: rule.route, reason: rule.reason, confidence: rule.confidence };
        }
        break;
      case "search":
        if (rule.unless?.test(stripped)) break;
        if (rule.regex.test(stripped)) {
          return { routeId: rule.route, reason: rule.reason, confidence: rule.confidence };
        }
        break;
      case "search_or_long": {
        const numbered = rule.numbered?.test(stripped) ?? false;
        const long = stripped.length > (rule.longChars ?? 0) || numbered;
        if (rule.regex.test(stripped) || long) {
          return { routeId: rule.route, reason: rule.reason, confidence: rule.confidence };
        }
        break;
      }
      default: {
        const unknown: never = rule.op;
        throw new DigillmRouterEngineError(`unknown rule op ${String(unknown)}`);
      }
    }
  }
  return undefined;
}

function centroidRoute(
  text: string,
  routes: readonly WorkingRoute[],
): { routeId: string; reason: string; confidence: number } | undefined {
  const query = vector(text);
  if (!query.some((value) => value !== 0)) return undefined;
  const scored = routes.map((route) => ({ score: cosine(query, centroid(route)), route }));
  scored.sort((left, right) => right.score - left.score);
  const best = scored[0];
  if (!best || best.score < TABLE.weak) return undefined;
  const confidence = Math.max(0, Math.min(1, (best.score + 1) / 2));
  return {
    routeId: best.route.id,
    reason: `Closest to the ${best.route.label} examples.`,
    confidence,
  };
}

function checked(
  routeId: string,
  label: string,
  model: string,
  reason: string,
  confidence: number,
  allow: readonly string[],
): DigillmRouterDecision {
  if (premiumModelIds().has(model)) {
    throw new DigillmRouterEngineError(`router will not use premium model ${model}`);
  }
  if (allow.length > 0 && !allow.includes(model)) {
    throw new DigillmRouterEngineError(`router chose ${model}, which is not on the allowlist`);
  }
  return { routeId, label, model, reason, confidence };
}

export type DigillmRouterEngineInput = {
  text: string;
  allowed: readonly string[];
  fallback: string;
  routes?: readonly DigillmRouterRouteInput[];
};

/** Same decision `digillm.router.route_query` returns for this input. */
export function decideDigillmRoute(input: DigillmRouterEngineInput): DigillmRouterDecision {
  const chosen = resolveRoutes(input.routes);
  if (chosen.length === 0) throw new DigillmRouterEngineError("router has no routes");
  const blocked = premiumModelIds();
  const raw = cleanAllow(input.allowed);
  const allow = raw.filter((item) => !blocked.has(item));
  if (raw.length > 0 && allow.length === 0) {
    throw new DigillmRouterEngineError("router will not use a premium model");
  }
  const usableFallback = blocked.has(input.fallback.trim()) ? "" : input.fallback;
  const bound = chosen.map((route) => ({ route, model: bindModel(route, allow, usableFallback) }));
  if (allow.length === 1) {
    const only = allow[0] ?? "";
    const match = bound.find((item) => item.model === only) ?? bound[0];
    if (!match) throw new DigillmRouterEngineError("router has no routes");
    return {
      routeId: match.route.id,
      label: match.route.label,
      model: only,
      reason: "Only one model is on the allowlist.",
      confidence: 1,
    };
  }
  const offered = bound.map((item) => item.route);
  const hit =
    ruleRoute(input.text, offered) ??
    (input.text.trim() ? centroidRoute(input.text, offered) : undefined);
  const byId = new Map(bound.map((item) => [item.route.id, item]));
  if (hit) {
    const found = byId.get(hit.routeId);
    if (!found) throw new DigillmRouterEngineError("router hit a route that is not on offer");
    return checked(found.route.id, found.route.label, found.model, hit.reason, hit.confidence, allow);
  }
  const model = defaultModel(allow, usableFallback);
  const reason = input.text.trim()
    ? "No strong signal — using the deployment default."
    : "Empty question — using the deployment default.";
  for (const item of bound) {
    if (item.model === model) {
      return checked(item.route.id, item.route.label, model, reason, 0.4, allow);
    }
  }
  return checked("auto", "Auto", model, reason, 0.4, allow);
}

function defaultModel(allow: readonly string[], fallback: string): string {
  const allowSet = new Set(allow);
  const auto = PRESETS.auto.trim();
  if (onAllowList(auto, allowSet)) return auto;
  const fallbackId = fallback.trim();
  if (onAllowList(fallbackId, allowSet)) return fallbackId;
  if (allow.length > 0 && allow[0]) return allow[0];
  throw new DigillmRouterEngineError("router has no model to choose");
}
