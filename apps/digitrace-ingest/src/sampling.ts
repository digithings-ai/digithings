/**
 * Head sampling.
 *
 * ADR-0036 §2 sets `head_sampling_rate = 1` (100%) on every source at launch and
 * leaves per-workflow rates to a later ticket. The rate lives on the *source*,
 * not on this Worker, so this module has one job: honour the rate the caller
 * hands it, deterministically, so a retried request makes the same decision and
 * a trace is never half-sampled.
 *
 * The decision is made once per trace id, on the low 32 bits of the trace id.
 * Sampling by trace id and not by span is what keeps a span tree whole.
 */
import { idBytes } from "./ids";

export const LAUNCH_SAMPLING_RATE = 1;

/** True when a rate is a usable sampling rate: a finite number in [0, 1]. */
export function isSamplingRate(rate: unknown): rate is number {
  return typeof rate === "number" && Number.isFinite(rate) && rate >= 0 && rate <= 1;
}

/**
 * The deterministic 32-bit value of a trace id, in [0, 1).
 *
 * Uses the last four bytes, the part a W3C random trace id varies most (the
 * first bytes of some generators are time-derived). Any fixed choice is
 * reproducible; this one is also unbiased across a generator's output.
 */
export function traceIdFraction(traceId: string): number {
  const bytes = idBytes(traceId);
  const offset = bytes.length - 4;
  const value =
    ((bytes[offset] << 24) >>> 0) +
    (bytes[offset + 1] << 16) +
    (bytes[offset + 2] << 8) +
    bytes[offset + 3];
  return value / 0x1_0000_0000;
}

/**
 * True when this trace is kept at `rate`.
 *
 * `rate >= 1` keeps everything and `rate <= 0` keeps nothing, without consulting
 * the id: a rate of 1 must be exactly 100%, and a comparison against a fraction
 * that can equal 1 would otherwise drop one trace in four billion.
 */
export function keepTrace(traceId: string, rate: number): boolean {
  if (!isSamplingRate(rate)) return false;
  if (rate >= 1) return true;
  if (rate <= 0) return false;
  return traceIdFraction(traceId) < rate;
}
