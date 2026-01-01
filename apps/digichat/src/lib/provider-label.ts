/**
 * Backend vocabulary for the digichat surfaces.
 *
 * The app owns the provider names; the UI package renders whatever label
 * the host hands it. `packages/ui` cannot import app code, so a provider id
 * hardcoded there would be a second, silently drifting copy of this list.
 */

import type { BYOKProvider } from "./byok-providers";

/** The house backend every digichat surface falls back to. */
export const HOUSE_BACKEND_ID = "cheaperinference";

/**
 * The backend that serves a chat right now, as a display label.
 *
 * An own-key provider wins when the session carries one; otherwise the chat
 * runs on the house backend. Provider ids are lowercase routing names and
 * the composer chip shows routing names, so the label is the id itself.
 */
export function backendLabel(
  byokProvider: BYOKProvider | null | undefined,
  backendType?: string,
): string {
  const own = byokProvider?.trim();
  if (own) return own;
  // A Foundry tenant is answered by its own agent, not by the house model
  // provider: naming the house backend there would be a lie.
  if (backendType === "foundry") return "Azure AI Foundry";
  return HOUSE_BACKEND_ID;
}
