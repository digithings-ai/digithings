import { DEPLOY_DEFAULT_MODELS } from "./deploy-config/deploy-models";

/**
 * Product hosts for digithings.ai. Their live tenant publishes
 * `models.available: []`, so the session model stays empty. The context
 * meter still needs a known window: `contextMeterModel` supplies the
 * catalog default for these slugs and does not write the session model.
 * OCC omits `models` and inherits the deploy catalog, so its session
 * model is that default and the meter follows it. A true flag on any
 * other slug does nothing.
 */
const HOUSE_CONTEXT_METER_SLUGS = new Set(["digithings", "digithings-ai"]);

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
 * Model id for the context meter only. A selected session model sizes the
 * bar. With none, the house slugs use the catalog default's window. That
 * id is not the session model and is not sent on the turn.
 */
export function contextMeterModel(input: {
  slug?: string;
  showContextMeter?: boolean;
  sessionModel?: string;
}): string {
  const selected = input.sessionModel?.trim() || "";
  if (selected) return selected;
  if (!contextMeterEnabled(input.showContextMeter, input.slug)) return "";
  return DEPLOY_DEFAULT_MODELS.default;
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
