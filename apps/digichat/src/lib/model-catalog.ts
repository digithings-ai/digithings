/**
 * Read-only access to the generated model catalog (#4994).
 *
 * The data itself lives in `model-catalog.generated.ts`, written by
 * `scripts/refresh_model_catalog.py` from `config/model-catalog.json`. That file
 * is ~330 KB, so import it from a server module only -- a client component that
 * pulls it in ships the whole catalog to the browser for no reason.
 *
 * This module holds no pricing or capability rules of its own. The generator
 * already derived `tier`; re-deriving it here would be the second copy of the
 * rule that this change exists to delete.
 */
import {
  MODEL_CATALOG_BY_PROVIDER,
  MODEL_CATALOG_BYOK_PROVIDER_MAP,
  MODEL_CATALOG_META,
} from "./model-catalog.generated";
import type { ByokModelOption, BYOKProvider } from "@/hooks/use-byok-key";

/** One normalized model row. Every optional field is `null` when upstream said
 * nothing -- "unknown" must never read as `false`. */
export type ModelCatalogEntry = {
  id: string;
  label: string;
  cost_input_usd_per_million: number | null;
  cost_output_usd_per_million: number | null;
  context_window: number | null;
  max_output_tokens: number | null;
  modalities_input: string[];
  modalities_output: string[];
  /** `null` when models.dev omitted the field -- distinct from a stated `false`. */
  tool_call: boolean | null;
  structured_output: boolean | null;
  reasoning: boolean;
  vision: boolean;
  attachment: boolean;
  open_weights: boolean;
  tier: "free" | "opensource" | "flagship" | null;
};

export type ModelCatalogBuckets = {
  free: ByokModelOption[];
  opensource: ByokModelOption[];
  flagship: ByokModelOption[];
  all: ByokModelOption[];
};

/** models.dev calls it `google`; digichat has always called it `gemini`. */
export const BYOK_PROVIDER_TO_CATALOG_PROVIDER: Readonly<Record<BYOKProvider, string>> =
  MODEL_CATALOG_BYOK_PROVIDER_MAP as Readonly<Record<BYOKProvider, string>>;

/** When the vendored snapshot was last refreshed from models.dev. */
export const MODEL_CATALOG_FETCHED_AT: string = MODEL_CATALOG_META.fetched_at;

const toOption = (entry: ModelCatalogEntry): ByokModelOption => ({
  id: entry.id,
  label: entry.label,
  ...(entry.tier ? { tier: entry.tier } : {}),
  // A stated `false` is a real upstream claim ("no tool calls") and is worth
  // passing on; an absent one is unknown, so the field is omitted rather than
  // defaulted to false -- the picker must not read silence as "no tools".
  ...(entry.tool_call !== null ? { supportsTools: entry.tool_call } : {}),
});

/**
 * Catalog rows for a BYOK provider. An unknown or unmapped provider yields
 * `[]` rather than throwing -- a suggestion list is not worth breaking a picker.
 */
export function catalogEntriesFor(byokProvider: string): readonly ModelCatalogEntry[] {
  const catalogProvider = BYOK_PROVIDER_TO_CATALOG_PROVIDER[
    byokProvider as BYOKProvider
  ];
  if (!catalogProvider) return [];
  return MODEL_CATALOG_BY_PROVIDER[catalogProvider] ?? [];
}

/**
 * Bucket by the tier the generator computed. `all` is sorted by id so the
 * picker's order is stable across refreshes; an unclassified entry (no price, or
 * upstream omitted one) appears in `all` only, never guessed into a bucket.
 */
export function bucketCatalogEntries(
  entries: readonly ModelCatalogEntry[],
): ModelCatalogBuckets {
  const all = [...entries]
    .sort((a, b) => a.id.localeCompare(b.id))
    .map(toOption);
  const inTier = (tier: NonNullable<ModelCatalogEntry["tier"]>) =>
    all.filter((option) => option.tier === tier);
  return {
    free: inTier("free"),
    opensource: inTier("opensource"),
    flagship: inTier("flagship"),
    all,
  };
}