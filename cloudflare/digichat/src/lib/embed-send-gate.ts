/**
 * Pre-send gate decisions for stock embed Thread.
 *
 * CliThread used to intercept via onSendRequest. Stock Composer submits through
 * assistant-ui's form → composer.send() with no hook into wrappedSend, so the
 * hold/charge path must be reattached at ComposerPrimitive.Root onSubmit.
 */

export type EmbedSendGateInput = {
  /** Free-tier counter has reached the limit. */
  locked: boolean;
  /** Trial-form path has raised the gate (server 402 or client ask). */
  trialLocked: boolean;
  /** Tenant is ungated (no free-tier / trial). */
  ungated: boolean;
  /** llmAccess === "byok_only" and visitor has not set a key. */
  byokRequired: boolean;
};

export type EmbedSendGateDecision =
  | { action: "send" }
  | { action: "hold_gate" }
  | { action: "hold_byok" };

/**
 * Decide whether a stock composer submit should reach POST /api/chat.
 * Empty text is ignored by the composer itself — callers should trim first.
 */
export function decideEmbedSendGate(input: EmbedSendGateInput): EmbedSendGateDecision {
  if (input.byokRequired) return { action: "hold_byok" };
  if (!input.ungated && (input.locked || input.trialLocked)) {
    return { action: "hold_gate" };
  }
  return { action: "send" };
}

/** Whether this allowed send should arm the free-tier charge-on-settle ref. */
export function shouldArmGateCharge(ungated: boolean): boolean {
  return !ungated;
}
