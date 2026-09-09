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
