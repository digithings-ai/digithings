/**
 * Curated digichat model picker. Prices, context, tool support, and the
 * preset rules live in `config/model-picker-catalog.json`. This module only
 * applies a deployment's cap and preset selection. It does not call a provider.
 */

import catalogJson from "../../config/model-picker-catalog.json";

export const PRESET_IDS = ["auto", "reasoning", "fast", "light", "router"] as const;
export type PresetId = (typeof PRESET_IDS)[number];

export type CatalogModel = {
  id: string;
  label: string;
  provider: string;
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
  description: string;
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
    minContextTokens: number;
    minTtftSamples: number;
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
  description: string;
  model: string;
};

export type ModelPickerGroup = {
  provider: string;
  models: { id: string; label: string }[];
};

export type ModelPickerView = {
  presets: ModelPickerPreset[];
  groups: ModelPickerGroup[];
  showFullList: boolean;
};

export type CatalogPolicy = {
  default?: string;
  priceCapUsdPerMillion?: number;
  presets?: readonly string[];
  showFullList?: boolean;
  minContextTokens?: number;
};

export type ResolvedCatalog = {
  available: string[];
  default: string;
  picker: ModelPickerView;
};

export function catalogSource(): string {
  return catalog.source;
}

function isPresetId(id: string): id is PresetId {
  return (PRESET_IDS as readonly string[]).includes(id);
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

function presetDef(id: PresetId): CatalogPresetDef | undefined {
  return catalog.presets.find((preset) => preset.id === id);
}

function autoModelId(): string {
  const model = presetDef("auto")?.model;
  if (!model) throw new Error("model catalog: auto preset has no model");
  return model;
}

function fill(template: string, label: string): string {
  return template.split("{label}").join(label);
}

/** Every routable catalog id, ignoring the price cap, plus configured routers. */
export function sessionAllowlistIds(): string[] {
  const models = catalog.models
    .filter((model) => passesFloor(model, catalog.policy.minContextTokens))
    .sort(byProviderThenPrice);
  const ids = models.map((model) => model.id);
  for (const router of catalog.routers) {
    if (!ids.includes(router.id)) ids.push(router.id);
  }
  return ids;
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
  const minContext = policy.minContextTokens ?? catalog.policy.minContextTokens;
  const minSamples = catalog.policy.minTtftSamples;
  const showFullList = policy.showFullList !== false;
  const requested = policy.presets ?? catalog.presets.map((preset) => preset.id);
  for (const id of requested) {
    if (!isPresetId(id)) throw new Error(`model catalog: unknown preset ${id}`);
  }
  const wanted = new Set(requested);

  const floored = catalog.models.filter((model) => passesFloor(model, minContext));
  const pinnedId = policy.default?.trim() || autoModelId();
  const pinned = floored.find((model) => model.id === pinnedId);
  if (!pinned) {
    throw new Error(
      "model catalog: default model is not in the catalog or is under the context floor",
    );
  }
  const capped = floored
    .filter((model) => model.outputPerM <= cap || model.id === pinned.id)
    .sort(byProviderThenPrice);

  const presets: ModelPickerPreset[] = [];

  if (wanted.has("auto")) {
    const def = presetDef("auto");
    const model = capped.find((row) => row.id === def?.model) ?? pinned;
    if (def) {
      presets.push({
        id: "auto",
        label: def.label,
        description: def.description,
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
        description: fill(def.description, winner.label),
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
        description: fill(def.description, winner.label),
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
        description: fill(def.description, winner.label),
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
        description: def.description,
        model: router.id,
      });
    }
  }

  const groups: ModelPickerGroup[] = [];
  if (showFullList) {
    for (const model of capped) {
      let group = groups.find((entry) => entry.provider === model.provider);
      if (!group) {
        group = { provider: model.provider, models: [] };
        groups.push(group);
      }
      group.models.push({ id: model.id, label: model.label });
    }
  }

  const available: string[] = [];
  const push = (id: string) => {
    if (id && !available.includes(id)) available.push(id);
  };
  if (showFullList) {
    for (const model of capped) push(model.id);
  }
  for (const preset of presets) push(preset.model);
  push(pinned.id);

  return {
    available,
    default: pinned.id,
    picker: { presets, groups, showFullList },
  };
}
