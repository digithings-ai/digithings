/**
 * Composer `/provider` flow (#3736). Same session BYOK contract as ByokCliFlow
 * (validate + ping, then activate). The public name is provider, not byok.
 */

import {
  BYOK_PROVIDER_LIST,
  byokModelPresets,
  byokRequiresModel,
  type BYOKProvider,
} from "@/hooks/use-byok-key";
import { isByokProvider } from "@/lib/byok-providers";

export const CUSTOM_PROVIDER_MODEL = "__custom__";

/** Composer list order: first-party providers, then the OpenRouter aggregator. */
export const PROVIDER_MENU_ORDER: readonly BYOKProvider[] = [
  "openai",
  "anthropic",
  "gemini",
  "xai",
  "openrouter",
];

/**
 * Row id of the clear-provider row that heads the rendered provider list.
 * It is not a BYOKProvider: it means "no provider key, use the default".
 */
export const CLEAR_PROVIDER_ROW_ID = "cheaperinference";

export type ProviderMenuRowId = typeof CLEAR_PROVIDER_ROW_ID | BYOKProvider;

/**
 * Rendered order of the provider menu rows: the clear row first, then the
 * provider order. The rendered rows and the cursor index both come from this
 * one list, so a prepended row can never shift the cursor.
 */
const PROVIDER_MENU_ROW_IDS: readonly ProviderMenuRowId[] = [
  CLEAR_PROVIDER_ROW_ID,
  ...PROVIDER_MENU_ORDER,
];

export function providerMenuRowIds(): readonly ProviderMenuRowId[] {
  return PROVIDER_MENU_ROW_IDS;
}

/**
 * Index of a provider inside the rendered provider rows. 0 is the clear row,
 * which is also the selected row when no provider key is connected.
 */
export function providerMenuRowIndex(provider?: BYOKProvider): number {
  if (!provider) return 0;
  const index = PROVIDER_MENU_ROW_IDS.indexOf(provider);
  return index >= 0 ? index : 0;
}

export function defaultProviderPick(
  active?: BYOKProvider,
  initial?: BYOKProvider,
): BYOKProvider {
  return active ?? initial ?? "openai";
}

const LIVE_PING_PROVIDERS: readonly BYOKProvider[] = ["openai", "anthropic", "gemini"];

export function wantsProviderKeyPing(provider: BYOKProvider): boolean {
  return LIVE_PING_PROVIDERS.includes(provider);
}

export function providerDisplayName(id: BYOKProvider): string {
  switch (id) {
    case "openrouter":
      return "OpenRouter";
    case "openai":
      return "OpenAI";
    case "anthropic":
      return "Anthropic";
    case "gemini":
      return "Gemini";
    case "xai":
      return "x.ai";
    default: {
      const _exhaustive: never = id;
      return _exhaustive;
    }
  }
}

export function providerKeyPlaceholder(provider: BYOKProvider): string {
  switch (provider) {
    case "openai":
      return "sk-…";
    case "anthropic":
      return "sk-ant-…";
    case "gemini":
      return "AIza…";
    case "xai":
      return "xai-…";
    case "openrouter":
      return "sk-or-v1-…";
    default: {
      const _exhaustive: never = provider;
      return _exhaustive;
    }
  }
}

export function tryResolveProviderInput(raw: string): BYOKProvider | undefined {
  const q = raw.trim().toLowerCase();
  if (!q) return undefined;
  if (isByokProvider(q)) return q;
  const hit = BYOK_PROVIDER_LIST.find((id) => providerDisplayName(id).toLowerCase() === q);
  return hit;
}

export function providerModelChoices(
  provider: BYOKProvider,
  live?: readonly { id: string; label: string }[],
): { id: string; label: string }[] {
  const rows = (live?.length ? live : byokModelPresets(provider).map((id) => ({ id, label: id }))).map(
    (m) => ({ id: m.id, label: m.label || m.id }),
  );
  const custom = { id: CUSTOM_PROVIDER_MODEL, label: "custom…" };
  if (!byokRequiresModel(provider)) {
    return [{ id: "", label: "(default)" }, ...rows, custom];
  }
  return [...rows, custom];
}

/** House CI picker until BYOK is connected; then that provider's catalog presets. */
export function sessionPickerModels(
  house: readonly string[],
  provider?: BYOKProvider | null,
): readonly string[] {
  if (provider) return byokModelPresets(provider);
  return house;
}
