import type { ByokModelOption } from "@/hooks/use-byok-key";

/** One entry from OpenRouter's public GET /api/v1/models catalog (fields we use).
 * Exact field names per OpenRouter's documented response shape — re-verify against
 * their live docs before depending on this in production; see the design spec's
 * caveat (this repo has no internet access to confirm it from a sandbox). */
export type OpenRouterCatalogEntry = {
  id: string;
  name?: string;
  pricing?: { prompt?: string; completion?: string };
  hugging_face_id?: string;
  supported_parameters?: string[];
};

/** Entries with no hugging_face_id fall back to this publisher-prefix allowlist for
 * the "opensource" tier — OpenRouter's schema has no universal open-weight signal,
 * unlike price (free/flagship), which is fully data-derived. Explicitly maintained;
 * expect to extend this list over time as new open-weight publishers appear. */
const OPEN_WEIGHT_PUBLISHER_PREFIXES = [
  "meta-llama/",
  "mistralai/",
  "qwen/",
  "deepseek/",
  "google/gemma",
  "thudm/",
  "zai/",
  "moonshotai/",
];

/** $ per 1M input tokens — at/above this, a model buckets as "flagship". Matches the
 * cheapest current frontier tier per docs/LLM_PROVIDERS.md's cheap-paid-API table.
 * A number, not a name list — a new frontier model qualifies the day it's priced,
 * no code change needed (unlike model_config.py's _FLAGSHIP_MODEL_ID_MARKERS). */
const FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M = 3;

export const OPENROUTER_CATALOG_ENTRY_CAP = 2000;

function promptPricePerMillion(entry: OpenRouterCatalogEntry): number | null {
  const raw = entry.pricing?.prompt;
  if (raw === undefined) return null;
  const perToken = Number(raw);
  if (!Number.isFinite(perToken)) return null;
  return perToken * 1_000_000;
}

function isFree(entry: OpenRouterCatalogEntry): boolean {
  const prompt = entry.pricing?.prompt;
  const completion = entry.pricing?.completion;
  if (prompt === undefined || completion === undefined) return false;
  const promptNum = Number(prompt);
  const completionNum = Number(completion);
  return (
    Number.isFinite(promptNum) &&
    promptNum === 0 &&
    Number.isFinite(completionNum) &&
    completionNum === 0
  );
}

function isOpenSource(entry: OpenRouterCatalogEntry): boolean {
  if (entry.hugging_face_id) return true;
  return OPEN_WEIGHT_PUBLISHER_PREFIXES.some((prefix) => entry.id.startsWith(prefix));
}

function isFlagship(entry: OpenRouterCatalogEntry): boolean {
  const price = promptPricePerMillion(entry);
  return price !== null && price >= FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M;
}

function tierFor(entry: OpenRouterCatalogEntry): NonNullable<ByokModelOption["tier"]> | undefined {
  if (isFree(entry)) return "free";
  if (isFlagship(entry)) return "flagship";
  if (isOpenSource(entry)) return "opensource";
  return undefined;
}

function supportsTools(entry: OpenRouterCatalogEntry): boolean {
  return Array.isArray(entry.supported_parameters) && entry.supported_parameters.includes("tools");
}

/** Bucket a live OpenRouter catalog into the BYOK picker's tiers. Caps total entries
 * processed — anything beyond the cap is silently dropped, never processed or returned
 * (see the design spec's Security considerations on unbounded response handling). */
export function bucketOpenRouterModels(entries: readonly OpenRouterCatalogEntry[]): OpenRouterCatalogBuckets {
  const capped = entries.slice(0, OPENROUTER_CATALOG_ENTRY_CAP);
  const all: ByokModelOption[] = [];
  const free: ByokModelOption[] = [];
  const opensource: ByokModelOption[] = [];
  const flagship: ByokModelOption[] = [];
  for (const entry of capped) {
    if (typeof entry.id !== "string" || !entry.id) continue;
    const option: ByokModelOption = {
      id: entry.id,
      label: entry.name?.trim() || entry.id,
      tier: tierFor(entry),
      supportsTools: supportsTools(entry),
    };
    all.push(option);
    if (option.tier === "free") free.push(option);
    else if (option.tier === "flagship") flagship.push(option);
    else if (option.tier === "opensource") opensource.push(option);
  }
  return { free, opensource, flagship, all };
}

export type OpenRouterCatalogBuckets = {
  free: ByokModelOption[];
  opensource: ByokModelOption[];
  flagship: ByokModelOption[];
  all: ByokModelOption[];
};
