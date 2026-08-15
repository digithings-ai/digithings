/**
 * Framework-neutral BYOK provider catalog + validation predicates.
 *
 * Deliberately carries NO "use client" directive: this module is imported by
 * the client-side `useBYOKKey()` hook (`hooks/use-byok-key.ts`) AND by two
 * server-side Next.js Route Handlers (`api/chat/route.ts`,
 * `api/byok/test/route.ts`) that cannot import a "use client" module. Before
 * this module existed, all three sites hand-maintained their own copy of the
 * provider list / prefix checks — a 6th provider added only to
 * `config/byok-providers.json` could silently be forwarded with no model
 * header, or a server route could silently treat an unrecognized provider
 * value as `"openai"`. See #2351.
 *
 * The catalog below mirrors (but is not generated from — see
 * `frontend/digichat/ARCHITECTURE.md`'s BYOK section) `config/byok-providers.json`.
 * `use-byok-key.catalog-parity.test.ts` fails if the two drift apart.
 */

import { isOpenRouterKey } from "@/lib/byok-openrouter";

export type BYOKProvider = "openai" | "anthropic" | "openrouter" | "gemini" | "xai";

type ByokProviderCatalogEntry = {
  id: BYOKProvider;
  keyPrefix: string;
  requiresModel: boolean;
};

/** Single source of truth for provider ids/order/requiresModel — every other
 * export below (BYOK_PROVIDER_LIST, byokRequiresModel, isByokProvider, ...)
 * is derived from this one array, not a second hand-kept copy of it. */
const BYOK_PROVIDER_CATALOG: readonly ByokProviderCatalogEntry[] = [
  { id: "openrouter", keyPrefix: "sk-or-", requiresModel: true },
  { id: "openai", keyPrefix: "sk-", requiresModel: false },
  { id: "anthropic", keyPrefix: "sk-ant-", requiresModel: true },
  { id: "gemini", keyPrefix: "AI", requiresModel: true },
  { id: "xai", keyPrefix: "xai-", requiresModel: true },
];

export const BYOK_PROVIDER_LIST: readonly BYOKProvider[] = BYOK_PROVIDER_CATALOG.map(
  (entry) => entry.id,
);

function findCatalogEntry(provider: string): ByokProviderCatalogEntry | undefined {
  return BYOK_PROVIDER_CATALOG.find((entry) => entry.id === provider);
}

/**
 * Type guard: does `value` name a known BYOK provider? Driven entirely by
 * `BYOK_PROVIDER_LIST` so a provider added there (and to the catalog above)
 * is recognized everywhere this guard is used, with no separate list to keep
 * in sync.
 */
export function isByokProvider(value: string): value is BYOKProvider {
  return (BYOK_PROVIDER_LIST as readonly string[]).includes(value);
}

/**
 * Parse a raw request-header/query value into a `BYOKProvider`, or `null`
 * when it names no known provider. Never silently coerces an unrecognized
 * value to a default provider (e.g. `"openai"`) — the caller must handle the
 * `null` case explicitly. Replaces the historical `readProvider` pattern that
 * fell through to `"openai"` for anything it didn't recognize.
 */
export function readByokProvider(raw: string): BYOKProvider | null {
  return isByokProvider(raw) ? raw : null;
}

/**
 * Non-OpenAI BYOK requires an explicit model slug (digigraph spend path).
 * Accepts a raw `string` — not narrowed to `BYOKProvider` — so an untyped
 * request-header value (e.g. `chat/route.ts`'s `x-byok-provider`) can be
 * checked directly with no unsafe cast. A value naming no known provider
 * returns `false`, the same as `"openai"` — this predicate is a pure gate on
 * whether a model header is required, not a provider-existence check (see
 * `readByokProvider`/`isByokProvider` for that).
 */
export function byokRequiresModel(provider: string): boolean {
  return findCatalogEntry(provider)?.requiresModel ?? false;
}

/**
 * Returns `null` if `key` matches `provider`'s required key prefix, or a
 * human-readable validation error otherwise. Does NOT check for an empty
 * key — callers that need that check do it themselves (see
 * `use-byok-key.ts`'s `validateBYOKKey`, which layers it on top). Shared by
 * the client hook's `validateBYOKKey` and `api/byok/test/route.ts`'s
 * prefix checks — previously two independently hand-maintained copies of
 * this rule (plus a third informal copy in the JSON catalog's own
 * `keyPrefix` field, checked for parity by
 * `use-byok-key.catalog-parity.test.ts`).
 */
export function byokKeyPrefixError(key: string, provider: BYOKProvider): string | null {
  if (provider === "openai" && !key.startsWith("sk-")) {
    return "OpenAI keys must start with sk-.";
  }
  if (provider === "anthropic" && !key.startsWith("sk-ant-")) {
    return "Anthropic keys must start with sk-ant-.";
  }
  if (provider === "openrouter" && !isOpenRouterKey(key)) {
    return "OpenRouter keys must start with sk-or-.";
  }
  if (provider === "gemini" && !key.startsWith("AI")) {
    return "Gemini keys must start with AI.";
  }
  if (provider === "xai" && !key.startsWith("xai-")) {
    return "x.ai keys must start with xai-.";
  }
  return null;
}
