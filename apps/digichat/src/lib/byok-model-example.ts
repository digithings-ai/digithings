/**
 * The BYOK provider's own first `fallbackModels` entry, for user-facing
 * "here is a model that provider serves" copy. Server-side only (#5029).
 *
 * Why this exists: `api/chat/route.ts`'s `byok_model_required` refusal used to
 * name three hardcoded model ids in a single sentence sent to *every* provider.
 * Two of those three are not served by the provider being told to use them — an
 * `xai` caller was told to send `openai/gpt-4o-mini`. A model list is only useful
 * remediation if the named model is one the reader's key can actually spend, and
 * `config/byok-providers.json` is where that fact is maintained.
 *
 * `digigraph/src/digigraph/llm_auth.py`'s `byok_model_example()` reads the same
 * file for the same reason, so the two refusals cannot drift apart.
 *
 * Deliberately a separate module from `byok-providers.ts`: that one is imported
 * by client components, and this one reaches outside the Next.js app root for the
 * repo-root catalog. Keeping them apart means the client bundle never pulls the
 * catalog in, and `next.config`'s `outputFileTracingRoot` (already the repo root)
 * is what makes the server-side import traceable.
 */
import byokCatalog from "../../../../config/byok-providers.json";

/**
 * `provider`'s own first `fallbackModels` entry, or `undefined` when the
 * provider is unknown or lists no models. Accepts a raw `string` — not narrowed
 * to `BYOKProvider` — because the value arrives from an untyped request header.
 */
export function byokModelExample(provider: string): string | undefined {
  const id = provider.trim().toLowerCase();
  return (
    (byokCatalog as { id: string; fallbackModels?: string[] }[]).find(
      (entry) => entry.id === id,
    )?.fallbackModels?.[0]
  );
}