/**
 * The exporter command line, shared by both TUI clients (DIG-2698).
 *
 * Every exporter takes flags of the same shape (`--flag value` or
 * `--flag=value`) and refuses everything else: an unknown flag or a stray word
 * must be an error, never silently ignored, or a mistyped option writes a
 * different record than the run intended.
 */

/**
 * Read `--flag value` and `--flag=value` pairs from an argument list.
 *
 * Throws on a word that is not a flag, a flag that is not in `known`, and a
 * flag with no value. The caller resolves paths and validates numbers.
 */
export function parseFlags(
  argv: string[],
  known: readonly string[],
): Map<string, string> {
  const values = new Map<string, string>();
  for (let index = 0; index < argv.length; index += 1) {
    const entry = argv[index];
    if (!entry.startsWith("--")) {
      throw new Error(`unexpected argument "${entry}" (unknown flag)`);
    }
    const equals = entry.indexOf("=");
    const name = equals === -1 ? entry : entry.slice(0, equals);
    if (!known.includes(name)) {
      throw new Error(`unknown flag "${name}"`);
    }
    let value: string | undefined;
    if (equals === -1) {
      value = argv[index + 1];
      index += 1;
    } else {
      value = entry.slice(equals + 1);
    }
    if (!value || value.startsWith("--")) {
      throw new Error(`${name} needs a value`);
    }
    values.set(name, value);
  }
  return values;
}

/** Read a positive integer flag value. */
export function positiveInt(value: string, flag: string): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(
      `${flag} needs a positive whole number (a positive number), got "${value}"`,
    );
  }
  return parsed;
}

/** A capture time must carry an explicit zone (`Z` or `±HH:MM`). */
const ZONED_ISO = /(?:Z|[+-]\d{2}:?\d{2})$/i;

/**
 * Read a capture-time flag and keep it as given.
 *
 * The timestamp is pinned so the committed fixture reproduces byte for byte:
 * without it `capturedAt` moves on every capture and no two runs agree.
 */
export function zonedIso(value: string, flag: string): string {
  const raw = value.trim();
  if (!ZONED_ISO.test(raw) || Number.isNaN(Date.parse(raw))) {
    throw new Error(
      `${flag} needs an ISO timestamp with a zone (e.g. 2026-10-22T05:45:00.000Z), got "${value}"`,
    );
  }
  return raw;
}
