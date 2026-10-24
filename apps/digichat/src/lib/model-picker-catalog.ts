/**
 * Curated digichat model picker. Prices, context, tool support, and the
 * preset rules live in `config/model-picker-catalog.json`. This module only
 * applies the newest-generation rule, then a deployment's cap and preset
 * selection. It does not call a provider.
 */

import catalogJson from "../../config/model-picker-catalog.json";

export const PRESET_IDS = ["auto", "reasoning", "fast", "light", "router"] as const;
export type PresetId = (typeof PRESET_IDS)[number];

export type CatalogModel = {
  id: string;
  label: string;
  provider: string;
  family: string;
  generation: number;
  released?: string;
  inputPerM: number;
  outputPerM: number;
  context: number;
  tools: boolean;
  reasoning: boolean;
  reasoningScore: number;
  ttftSamples: number;
  ttftP50Ms: number;
  tags: string[];
};

type CatalogPresetDef = {
  id: PresetId;
  label: string;
  model?: string;
  requires?: string;
};

type CatalogRouter = {
  id: string;
  provider: string;
  requires?: string;
  passesAllowlist?: boolean;
};

type CatalogFile = {
  source: string;
  policy: {
    priceCapUsdPerMillion: number;
    premiumCapUsdPerMillion: number;
    minContextTokens: number;
    minTtftSamples: number;
    latestGenerationsPerFamily: number;
    maxAgeDays: number | null;
    asOf: string;
  };
  providerOrder: string[];
  presets: CatalogPresetDef[];
  routers: CatalogRouter[];
  models: CatalogModel[];
};

const catalog = catalogJson as CatalogFile;

export type ModelPickerPreset = {
  id: string;
  label: string;
  model: string;
};

export type ModelPickerGroup = {
  /** Backend provider id: the model id prefix before the first "/". */
  provider: string;
  models: { id: string; label: string; premium?: boolean }[];
  /** A hand-written group can still be manual-only. The catalog never sets it. */
  premium?: boolean;
};

export type ModelPickerView = {
  presets: ModelPickerPreset[];
  groups: ModelPickerGroup[];
  showFullList: boolean;
};

export type CatalogPolicy = {
  default?: string;
  priceCapUsdPerMillion?: number;
  premiumCapUsdPerMillion?: number;
  presets?: readonly string[];
  showFullList?: boolean;
  minContextTokens?: number;
  latestGenerationsPerFamily?: number;
  maxAgeDays?: number | null;
};

export type ResolvedCatalog = {
  available: string[];
  default: string;
  picker: ModelPickerView;
};

export function catalogModelRate(
  id: string,
): { inputPerM: number; outputPerM: number } | undefined {
  const row = catalog.models.find((model) => model.id === id);
  if (!row) return undefined;
  return { inputPerM: row.inputPerM, outputPerM: row.outputPerM };
}

/** Ids marked premium, on the model or on a hand-written manual-only group. */
export function premiumIdsFromGroups(
  groups:
    | readonly {
        premium?: boolean;
        models: readonly { id: string; premium?: boolean }[];
      }[]
    | undefined,
): string[] {
  if (!groups) return [];
  const ids: string[] = [];
  for (const group of groups) {
    for (const model of group.models) {
      if (!group.premium && !model.premium) continue;
      if (!ids.includes(model.id)) ids.push(model.id);
    }
  }
  return ids;
}

function isPresetId(id: string): id is PresetId {
  return (PRESET_IDS as readonly string[]).includes(id);
}

/** Backend provider id: the part of a model id before the first "/". */
export function providerIdOf(id: string): string {
  const at = id.indexOf("/");
  return at > 0 ? id.slice(0, at) : id;
}

function providerRank(provider: string): number {
  const index = catalog.providerOrder.indexOf(provider);
  return index === -1 ? catalog.providerOrder.length : index;
}

function byProviderThenPrice(a: CatalogModel, b: CatalogModel): number {
  const rank = providerRank(a.provider) - providerRank(b.provider);
  if (rank !== 0) return rank;
  if (a.provider !== b.provider) return a.provider.localeCompare(b.provider);
  if (a.outputPerM !== b.outputPerM) return a.outputPerM - b.outputPerM;
  const label = a.label.localeCompare(b.label);
  if (label !== 0) return label;
  return a.id.localeCompare(b.id);
}

function passesFloor(model: CatalogModel, minContext: number): boolean {
  return model.tools === true && model.context >= minContext;
}

const MS_PER_DAY = 86_400_000;

function ageDays(asOf: string, released: string): number | null {
  const end = Date.parse(`${asOf}T00:00:00Z`);
  const start = Date.parse(`${released}T00:00:00Z`);
  if (Number.isNaN(end) || Number.isNaN(start)) return null;
  return Math.floor((end - start) / MS_PER_DAY);
}

/**
 * Tool-capable models at or above the context floor, limited to the newest
 * generations of each family. A max age drops a dated row; a row with no
 * release date stays. The price cap is applied later.
 */
function generationWindow(policy: CatalogPolicy): CatalogModel[] {
  const minContext = policy.minContextTokens ?? catalog.policy.minContextTokens;
  const latestN =
    policy.latestGenerationsPerFamily ?? catalog.policy.latestGenerationsPerFamily;
  const maxAge = policy.maxAgeDays !== undefined ? policy.maxAgeDays : catalog.policy.maxAgeDays;
  if (!Number.isInteger(latestN) || latestN < 1) {
    throw new Error("model catalog: latestGenerationsPerFamily must be a positive integer");
  }
  const floored = catalog.models.filter((model) => passesFloor(model, minContext));
  const byFamily = new Map<string, CatalogModel[]>();
  for (const model of floored) {
    if (!model.family || typeof model.generation !== "number") {
      throw new Error(`model catalog: ${model.id} has no family or generation`);
    }
    const rows = byFamily.get(model.family) ?? [];
    rows.push(model);
    byFamily.set(model.family, rows);
  }
  const kept: CatalogModel[] = [];
  for (const rows of byFamily.values()) {
    const generations = [...new Set(rows.map((row) => row.generation))].sort((a, b) => b - a);
    const keep = new Set(generations.slice(0, latestN));
    for (const row of rows) {
      if (!keep.has(row.generation)) continue;
      if (typeof maxAge === "number" && row.released) {
        const age = ageDays(catalog.policy.asOf, row.released);
        if (age !== null && age > maxAge) continue;
      }
      kept.push(row);
    }
  }
  return kept;
}

function presetDef(id: PresetId): CatalogPresetDef | undefined {
  return catalog.presets.find((preset) => preset.id === id);
}

function autoModelId(): string {
  const model = presetDef("auto")?.model;
  if (!model) throw new Error("model catalog: auto preset has no model");
  return model;
}

/** Auto preset model. The over-budget fallback uses this when a deployment has no default. */
export function autoPresetModelId(): string {
  return autoModelId();
}

/**
 * digigraph's session allowlist: the published picker. That is the standard
 * models at the $2 cap plus the premium tier at or under the $2.50 premium
 * cap. No router, and nothing above the premium cap. digigraph is
 * the last hop before a bill, so it must not bind an id the premium cap
 * excludes even if a hand-written `available` list on some host offers one.
 * Raising a cap means raising this list and DIGI_SESSION_MODEL_ALLOWLIST.
 */
export function sessionAllowlistIds(): string[] {
  return resolveModelCatalog({}, { openRouterConfigured: false }).available;
}

/**
 * Filter the catalog for one deployment. `openRouterConfigured` is a boolean
 * the server computed from whether a key is present. This function never
 * reads the environment.
 */
export function resolveModelCatalog(
  policy: CatalogPolicy,
  opts: { openRouterConfigured: boolean },
): ResolvedCatalog {
  const cap = policy.priceCapUsdPerMillion ?? catalog.policy.priceCapUsdPerMillion;
  const premiumCap =
    policy.premiumCapUsdPerMillion ?? catalog.policy.premiumCapUsdPerMillion;
  const minSamples = catalog.policy.minTtftSamples;
  const showFullList = policy.showFullList !== false;
  const requested = policy.presets ?? catalog.presets.map((preset) => preset.id);
  for (const id of requested) {
    if (!isPresetId(id)) throw new Error(`model catalog: unknown preset ${id}`);
  }
  const wanted = new Set(requested);

  const current = generationWindow(policy);
  const pinnedId = policy.default?.trim() || autoModelId();
  const pinned = current.find((model) => model.id === pinnedId);
  if (!pinned) {
    throw new Error(
      "model catalog: default model is not in the current generation or is under the context floor",
    );
  }
  const standard = current
    .filter((model) => model.outputPerM <= cap || model.id === pinned.id)
    .sort(byProviderThenPrice);
  const premium = current
    .filter(
      (model) =>
        model.id !== pinned.id && model.outputPerM > cap && model.outputPerM <= premiumCap,
    )
    .sort(byProviderThenPrice);
  const capped = standard;

  const presets: ModelPickerPreset[] = [];

  if (wanted.has("auto")) {
    const def = presetDef("auto");
    const model = capped.find((row) => row.id === def?.model) ?? pinned;
    if (def) {
      presets.push({
        id: "auto",
        label: def.label,
        model: model.id,
      });
    }
  }

  if (wanted.has("reasoning")) {
    const def = presetDef("reasoning");
    const winner = capped
      .filter((model) => model.reasoning && model.reasoningScore > 0)
      .sort(
        (a, b) =>
          b.reasoningScore - a.reasoningScore ||
          a.outputPerM - b.outputPerM ||
          a.id.localeCompare(b.id),
      )[0];
    if (def && winner) {
      presets.push({
        id: "reasoning",
        label: def.label,
        model: winner.id,
      });
    }
  }

  if (wanted.has("fast")) {
    const def = presetDef("fast");
    const winner = capped
      .filter((model) => model.ttftSamples >= minSamples && model.ttftP50Ms > 0)
      .sort((a, b) => a.ttftP50Ms - b.ttftP50Ms || a.id.localeCompare(b.id))[0];
    if (def && winner) {
      presets.push({
        id: "fast",
        label: def.label,
        model: winner.id,
      });
    }
  }

  if (wanted.has("light")) {
    const def = presetDef("light");
    const winner = [...capped].sort(
      (a, b) =>
        a.outputPerM - b.outputPerM || a.inputPerM - b.inputPerM || a.id.localeCompare(b.id),
    )[0];
    if (def && winner) {
      presets.push({
        id: "light",
        label: def.label,
        model: winner.id,
      });
    }
  }

  if (wanted.has("router") && opts.openRouterConfigured) {
    const def = presetDef("router");
    const router = catalog.routers.find((entry) => entry.requires === def?.requires);
    if (def && router) {
      presets.push({
        id: "router",
        label: def.label,
        model: router.id,
      });
    }
  }

  const groups: ModelPickerGroup[] = [];
  if (showFullList) {
    // One group per backend provider id, laid out as a collapsible tree in the
    // picker. Premium models stay under their own provider and carry the flag;
    // there is no separate manual group. Providers and ids sort alphabetically
    // so the tree is stable between visits.
    const byProvider = new Map<string, ModelPickerGroup["models"]>();
    const premiumIds = new Set(premium.map((model) => model.id));
    for (const model of [...capped, ...premium]) {
      const provider = providerIdOf(model.id);
      const rows = byProvider.get(provider) ?? [];
      rows.push({
        id: model.id,
        label: model.label,
        ...(premiumIds.has(model.id) ? { premium: true } : {}),
      });
      byProvider.set(provider, rows);
    }
    for (const provider of [...byProvider.keys()].sort((a, b) => a.localeCompare(b))) {
      const rows = byProvider.get(provider) ?? [];
      rows.sort((a, b) => a.id.localeCompare(b.id));
      groups.push({ provider, models: rows });
    }
  }

  const available: string[] = [];
  const push = (id: string) => {
    if (id && !available.includes(id)) available.push(id);
  };
  if (showFullList) {
    for (const model of capped) push(model.id);
    for (const model of premium) push(model.id);
  }
  for (const preset of presets) push(preset.model);
  push(pinned.id);

  return {
    available,
    default: pinned.id,
    picker: { presets, groups, showFullList },
  };
}
