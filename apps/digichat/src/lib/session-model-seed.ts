import { contextWindowFor } from "@digithings/ui/chat/context-meter";

/**
 * Product hosts for digithings.ai. `contextMeterEnabled` is the toolbar
 * render gate: on for slugs `digithings` and `digithings-ai` unless the
 * flag is explicitly false, and off for every other slug. The live house
 * tenant publishes no models, so this release shows no house bar.
 * Digigraph reporting the model it served is a 2.6.8 follow-up and is
 * not implemented here.
 */
const HOUSE_CONTEXT_METER_SLUGS = new Set(["digithings", "digithings-ai"]);

/** Toolbar render gate. An omitted flag is on for the house slugs only. */
export function contextMeterEnabled(
  showContextMeter: boolean | undefined,
  slug: string | undefined,
): boolean {
  if (showContextMeter === false) return false;
  return slug !== undefined && HOUSE_CONTEXT_METER_SLUGS.has(slug);
}

/**
 * Model id written into the session on first paint, and the only id that
 * may leave as X-Digi-Model.
 *
 * A non-empty `available` list wins: the curated default, else the first
 * entry. An empty list stays empty. The context meter sizes itself from
 * `contextMeterModel` instead, so showing the bar does not pick a model.
 */
export function sessionModelSeed(input: {
  available: readonly string[];
  defaultModel?: string;
}): string {
  const named = input.defaultModel?.trim() || "";
  if (input.available.length > 0) {
    return named || input.available[0] || "";
  }
  return "";
}

/**
 * Model id whose context window the bar draws.
 *
 * A reported id with its own window is the model that served the turn.
 * A reported id with no window falls back to the session model, so OCC
 * keeps its bar. An empty session and no known report resolve to "".
 * This id is never written into the session.
 */
export function contextMeterModel(input: {
  sessionModel?: string;
  reportedModel?: string;
}): string {
  const reported = input.reportedModel?.trim() || "";
  const session = input.sessionModel?.trim() || "";
  if (reported && contextWindowFor(reported) !== undefined) return reported;
  return session;
}

/**
 * Model id `getSelectedModel` returns. Empty means the turn sends no
 * X-Digi-Model. BYOK's bound model wins, matching the embed callback.
 */
export function modelSentOnTurn(
  sessionModel: string,
  byok?: { isSet: boolean; model: string },
): string | undefined {
  if (byok?.isSet) {
    const bound = byok.model.trim();
    if (bound) return bound;
  }
  const id = sessionModel.trim();
  return id || undefined;
}

/** Model chip in the composer footer. A known window for the meter is not a picker. */
export function showModelPicker(input: {
  allowPicker?: boolean;
  featureModelPicker?: boolean;
  available: readonly string[];
}): boolean {
  return (
    (input.allowPicker === true || input.featureModelPicker === true) && input.available.length > 0
  );
}
