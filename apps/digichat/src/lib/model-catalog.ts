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
  MODEL_CATALOG_ROUTABLE_BYOK_MODEL_IDS,
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
  /** `null` when models.dev omitted the field. All three of `reasoning`,
   * `attachment` and `open_weights` are tri-state upstream: the generator emits
   * `null` for an absent flag, so these are `boolean | null` too. Typing them
   * as plain `boolean` would let the first refresh that sees an omitted flag
   * land a red `next build` while `--check` still reports the artifacts in sync. */
  reasoning: boolean | null;
  vision: boolean;
  attachment: boolean | null;
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
 * Catalog rows for a BYOK provider that the house can actually route.
 *
 * models.dev is a curated metadata database, not a routing registry, so
 * membership in the catalog is **not** evidence that a model is servable:
 * `config/litellm.yaml` routes strictly (no `fallbacks`), so an id with no
 * declared `model_name` is a 500 waiting to happen, and of anthropic's 16
 * catalog rows *zero* have a LiteLLM group. The routable set is generated from
 * the LiteLLM configs themselves (`MODEL_CATALOG_ROUTABLE_BYOK_MODEL_IDS`), so
 * this filter is an intersection, not a second opinion about routability.
 *
 * A provider whose routable set is empty -- anthropic today -- yields `[]`,
 * which the picker treats as "no catalog list" and falls back to
 * `byokModelPresets`. That is today's behaviour for those providers, unchanged.
 *
 * An unknown or unmapped provider yields `[]` rather than throwing -- a
 * suggestion list is not worth breaking a picker.
 */
export function catalogEntriesFor(byokProvider: string): readonly ModelCatalogEntry[] {
  const catalogProvider = BYOK_PROVIDER_TO_CATALOG_PROVIDER[
    byokProvider as BYOKProvider
  ];
  if (!catalogProvider) return [];
  const routable = new Set(
    MODEL_CATALOG_ROUTABLE_BYOK_MODEL_IDS[byokProvider as BYOKProvider] ?? [],
  );
  const entries = MODEL_CATALOG_BY_PROVIDER[catalogProvider] ?? [];
  // The generated ids and the generated routable ids are both author-prefixed
  // the same way, so this is a plain set membership -- no suffix matching.
  return entries.filter((entry) => routable.has(entry.id));
}

/**
 * Bucket by the tier the generator computed. The generator already sorted each
 * provider's rows by id, so the order is inherited rather than re-derived: a
 * `localeCompare` here would make the picker's order depend on the server's
 * locale (2 of 10 providers reorder under `en-CA`), which is not what
 * `config/model-catalog.json` and `docs/MODEL_CATALOG.md` promise.
 * An unclassified entry (no price, or upstream omitted one) appears in `all`
 * only, never guessed into a bucket.
 */
export function bucketCatalogEntries(
  entries: readonly ModelCatalogEntry[],
): ModelCatalogBuckets {
  const all = entries.map(toOption);
  const inTier = (tier: NonNullable<ModelCatalogEntry["tier"]>) =>
    all.filter((option) => option.tier === tier);
  return {
    free: inTier("free"),
    opensource: inTier("opensource"),
    flagship: inTier("flagship"),
    all,
  };
}