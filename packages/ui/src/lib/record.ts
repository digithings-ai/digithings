/**
 * The one JSON-object reader.
 *
 * `asRecord` / `isRecord` had been hand-copied into app modules, and the copies
 * drifted in two ways: some versions let arrays through as records, and some
 * returned `{}` where the caller expected `null`. A record here is a parsed
 * JSON object and nothing else — an array is not a record, because every caller
 * reads a named key off the result and an array answers `undefined` to every
 * key, silently.
 */

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Narrow to a record, or `null` when the value is anything else. */
export function asRecord(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}
