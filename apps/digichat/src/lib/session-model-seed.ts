/**
 * Product hosts for digithings.ai. Their live tenant publishes
 * `models.available: []`, so the session model stays empty and a turn
 * sends no X-Digi-Model. The context meter then uses the model id the
 * turn reports, not the deploy catalog default. OCC omits `models` and
 * inherits the deploy catalog, so its session model is that default.
 * A true flag on any other slug does nothing.
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
 * Model id whose context window the bar draws.
 *
 * The id the turn reported is the one that served it. With no report yet,
 * the session model is the id the next turn will send. An empty session
 * and no report resolve to "" — the catalog default is not a stand-in,
 * and this id is never written into the session.
 */
export function contextMeterModel(input: {
  sessionModel?: string;
  reportedModel?: string;
}): string {
  const reported = input.reportedModel?.trim() || "";
  if (reported) return reported;
  return input.sessionModel?.trim() || "";
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
