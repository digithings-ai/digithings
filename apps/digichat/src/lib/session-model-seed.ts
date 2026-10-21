import { DEPLOY_DEFAULT_MODELS } from "./deploy-config/deploy-models";

/**
 * Product hosts for digithings.ai. Their live tenant publishes
 * `models.available: []`, so the session model stays empty and the context
 * meter (which needs a known window) renders nothing. OCC omits `models`
 * and inherits the deploy catalog, which is why that host shows the meter.
 * These slugs seed the same catalog default unless `showContextMeter` is false.
 * A true flag on any other slug does nothing: the seed must not put the
 * house catalog on a tenant the bridge keeps off it.
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
 * Model id written into the composer on first paint.
 *
 * A non-empty `available` list wins: the curated default, else the first
 * entry. An empty list seeds the catalog default only when the context
 * meter is enabled for this host. The picker stays closed — that decision
 * is `showModelPicker`, which still requires a non-empty list.
 */
export function sessionModelSeed(input: {
  slug?: string;
  available: readonly string[];
  defaultModel?: string;
  showContextMeter?: boolean;
}): string {
  const named = input.defaultModel?.trim() || "";
  if (input.available.length > 0) {
    return named || input.available[0] || "";
  }
  if (!contextMeterEnabled(input.showContextMeter, input.slug)) return "";
  return named || DEPLOY_DEFAULT_MODELS.default;
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
