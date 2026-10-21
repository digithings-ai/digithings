/**
 * Client-safe names for digillm's router.
 *
 * The decision itself is `digillm.router`. The chat route runs the TypeScript
 * port by default. This module only knows the picker id and which backends
 * can apply a per-turn model. It does not score and it does not spawn — this
 * file is imported by client components.
 */

export const DIGILLM_ROUTER_MODEL_ID = "digillm/router";

/** Backends whose stream call takes the model id the router returns. */
const ROUTER_BACKENDS: ReadonlySet<string> = new Set([
  "digigraph",
  "openai-completions",
  "openai-responses",
  "anthropic",
  "google-vertex",
]);

export function isDigillmRouterModel(id: string | null | undefined): boolean {
  return (id ?? "").trim() === DIGILLM_ROUTER_MODEL_ID;
}

export function digillmRouterOffered(input: {
  enabled: boolean | undefined;
  backendType: string | undefined;
}): boolean {
  return input.enabled === true && ROUTER_BACKENDS.has(input.backendType ?? "");
}

type TextPart = { type?: string; text?: string };
type RoutedMessage = { role?: string; parts?: readonly TextPart[] };

/** The latest user text, ignoring file parts (page context is a file). */
export function latestUserText(messages: readonly RoutedMessage[] | undefined): string {
  if (!messages?.length) return "";
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message?.role !== "user") continue;
    const text = (message.parts ?? [])
      .filter((part) => part.type === "text" && typeof part.text === "string")
      .map((part) => (part.text ?? "").trim())
      .filter(Boolean)
      .join("\n")
      .trim();
    if (text) return text.slice(0, 4000);
  }
  return "";
}

export type DigillmRouterDecision = {
  routeId: string;
  label: string;
  model: string;
  reason: string;
  confidence: number;
};

export type DigillmRouterRouteInput = {
  id: string;
  label: string;
  description: string;
  model?: string;
  exemplars?: string[];
};
