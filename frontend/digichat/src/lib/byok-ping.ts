import { p } from "@/lib/base-path";
import {
  byokRequiresModel,
  type BYOKProvider,
  validateBYOKKey,
  validateBYOKModel,
} from "@/hooks/use-byok-key";

export type ByokPingResult = { ok: boolean; model?: string; error?: string };

/**
 * Client-side ping against `POST /api/byok/test`.
 * Key travels only in the request header for this call — never persisted by the BFF.
 */
export async function pingByokKey(
  key: string,
  provider: BYOKProvider,
  model: string,
): Promise<ByokPingResult> {
  const formatErr =
    validateBYOKKey(key, provider) ?? validateBYOKModel(model, provider);
  if (formatErr) {
    return { ok: false, error: formatErr };
  }

  const headers: Record<string, string> = {
    "content-type": "application/json",
    "X-BYOK-Key": key,
    "X-BYOK-Provider": provider,
  };
  if (byokRequiresModel(provider) || model.trim()) {
    headers["X-BYOK-Model"] = model.trim();
  }

  try {
    const resp = await fetch(p("/api/byok/test"), {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({}),
    });
    const data = (await resp.json()) as ByokPingResult;
    if (!resp.ok && data.ok !== false) {
      return { ok: false, error: data.error ?? `HTTP ${resp.status}` };
    }
    return data;
  } catch {
    return { ok: false, error: "Network error — could not reach server." };
  }
}

/**
 * Gate used before activating BYOK in session memory.
 * Returns an error string when activation must be refused.
 */
export function byokActivationGate(
  ping: ByokPingResult | null,
): string | null {
  if (!ping) return "Validate the key before continuing.";
  if (!ping.ok) return ping.error ?? "Validation failed.";
  return null;
}
