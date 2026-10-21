/**
 * Preset resolution for digillm's router.
 *
 * Same rules as `digillm.router.catalog`: newest generation of each family,
 * then the standard output-price cap. `premium: true` (or a price above that
 * cap and at or under the premium cap) is manual selection only.
 */

import catalogJson from "../../../../digillm/src/digillm/router/model_catalog.json";

export type ResolvedPresets = {
  auto: string;
  reasoning: string;
  fast: string;
  light: string;
};

type CatalogModel = {
  id: string;
  family: string;
  generation: number;
  inputPerM: number;
  outputPerM: number;
  context: number;
  tools: boolean;
  reasoning: boolean;
  reasoningScore: number;
  ttftSamples: number;
  ttftP50Ms: number;
  released?: string;
  premium?: boolean;
};

type CatalogFile = {
  policy: {
    priceCapUsdPerMillion: number;
    premiumCapUsdPerMillion: number;
    minContextTokens: number;
    minTtftSamples: number;
    latestGenerationsPerFamily: number;
    maxAgeDays: number | null;
    asOf: string;
  };
  presets: { id: string; model?: string }[];
  models: CatalogModel[];
};

const MS_PER_DAY = 86_400_000;
const catalog = catalogJson as CatalogFile;

function ageDays(asOf: string, released: string): number | null {
  const end = Date.parse(`${asOf}T00:00:00Z`);
  const start = Date.parse(`${released}T00:00:00Z`);
  if (Number.isNaN(end) || Number.isNaN(start)) return null;
  return Math.floor((end - start) / MS_PER_DAY);
}

function generationWindow(): CatalogModel[] {
  const { policy } = catalog;
  const latestN = policy.latestGenerationsPerFamily;
  if (!Number.isInteger(latestN) || latestN < 1) {
    throw new Error("model catalog: latestGenerationsPerFamily must be a positive integer");
  }
  const floored = catalog.models.filter(
    (model) => model.tools === true && model.context >= policy.minContextTokens,
  );
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
      if (typeof policy.maxAgeDays === "number" && row.released) {
        const age = ageDays(policy.asOf, row.released);
        if (age !== null && age > policy.maxAgeDays) continue;
      }
      kept.push(row);
    }
  }
  return kept;
}

function isPremium(model: CatalogModel, pinnedId: string): boolean {
  if (model.premium) return true;
  if (model.id === pinnedId) return false;
  const { priceCapUsdPerMillion, premiumCapUsdPerMillion } = catalog.policy;
  return model.outputPerM > priceCapUsdPerMillion && model.outputPerM <= premiumCapUsdPerMillion;
}

/** Newest-generation models the picker marks manual-only. */
export function premiumModelIds(): ReadonlySet<string> {
  const pinnedId = catalog.presets.find((preset) => preset.id === "auto")?.model ?? "";
  const window = new Set(generationWindow().map((model) => model.id));
  return new Set(
    catalog.models
      .filter((model) => window.has(model.id) && isPremium(model, pinnedId))
      .map((model) => model.id),
  );
}

/** Auto, Reasoning, Fast, and Light for the catalog's standard cap. */
export function resolveDigillmPresets(): ResolvedPresets {
  const cap = catalog.policy.priceCapUsdPerMillion;
  const minSamples = catalog.policy.minTtftSamples;
  const current = generationWindow();
  const pinnedId = catalog.presets.find((preset) => preset.id === "auto")?.model ?? "";
  const pinned = current.find((model) => model.id === pinnedId);
  if (!pinned) {
    throw new Error(
      "model catalog: default model is not in the current generation or is under the context floor",
    );
  }
  const blocked = premiumModelIds();
  const capped = current.filter(
    (model) => !blocked.has(model.id) && (model.outputPerM <= cap || model.id === pinned.id),
  );
  const reasoning = capped
    .filter((model) => model.reasoning && model.reasoningScore > 0)
    .sort(
      (a, b) =>
        b.reasoningScore - a.reasoningScore ||
        a.outputPerM - b.outputPerM ||
        a.id.localeCompare(b.id),
    )[0];
  const fast = capped
    .filter((model) => model.ttftSamples >= minSamples && model.ttftP50Ms > 0)
    .sort((a, b) => a.ttftP50Ms - b.ttftP50Ms || a.id.localeCompare(b.id))[0];
  const light = [...capped].sort(
    (a, b) => a.outputPerM - b.outputPerM || a.inputPerM - b.inputPerM || a.id.localeCompare(b.id),
  )[0];
  if (!reasoning || !fast || !light) {
    throw new Error("model catalog: a preset has no model under the cap");
  }
  return {
    auto: pinned.id,
    reasoning: reasoning.id,
    fast: fast.id,
    light: light.id,
  };
}
