/**
 * Read the parts of wrangler.toml this Worker must agree with (DIG-732).
 *
 * The deployable trigger list and the identity of the Worker are facts in the
 * file, so the checks that read them read the file. A copy of the cron list
 * pasted into a test is a second source of truth that drifts silently, which is
 * how the `twelve-x-session-catchup` backstop could be deleted from both the
 * job map and the deploy config while every assertion stayed green.
 *
 * Pure text handling on purpose: no TOML dependency, no fs. Callers pass the
 * file text, which is what makes the deletion scenarios below writable as
 * "remove this line from this file".
 */

type TomlField = (line: string) => RegExpExecArray | null;

function field(text: string, name: string, pattern: TomlField): string {
  for (const line of text.split("\n")) {
    const match = pattern(line);
    if (match) return match[1];
  }
  throw new Error(`wrangler.toml has no ${name}`);
}

function singleQuoted(line: string, name: string): RegExpExecArray | null {
  return new RegExp(`^\\s*${name}\\s*=\\s*"([^"]*)"`).exec(line);
}

/** The Worker script name. The schedule API is addressed by it. */
export function workerNameFromWranglerToml(text: string): string {
  return field(text, "name", (line) => singleQuoted(line, "name"));
}

/** The account that owns the Worker. Also the account the schedule API needs. */
export function accountIdFromWranglerToml(text: string): string {
  return field(text, "account_id", (line) => singleQuoted(line, "account_id"));
}

/**
 * Cron expressions in `[triggers].crons`, in file order.
 *
 * Trailing `# job-id` comments are ignored. Reading stops at the closing bracket
 * of the crons list, so a later table can never contribute expressions.
 */
export function cronsFromWranglerToml(text: string): string[] {
  const lines = text.split("\n");
  const start = lines.findIndex((line) => line.trim() === "[triggers]");
  if (start < 0) throw new Error("wrangler.toml has no [triggers] table");
  const out: string[] = [];
  let inList = false;
  let closed = false;
  for (const line of lines.slice(start + 1)) {
    const trimmed = line.trim();
    if (closed) break;
    if (!inList) {
      // Any other table ends the section; anything else is a key we do not read.
      if (trimmed.startsWith("[")) break;
      if (/^crons\s*=/.test(trimmed)) inList = true;
      continue;
    }
    if (trimmed.startsWith("]")) {
      closed = true;
      break;
    }
    const match = /"([^"]*)"/.exec(trimmed);
    if (match) out.push(match[1]);
  }
  if (!inList) throw new Error("wrangler.toml [triggers] has no crons list");
  return out;
}

/** Remove every line containing `needle`. The shape of the deletion scenarios. */
export function withoutLine(text: string, needle: string): string {
  const lines = text.split("\n");
  const kept = lines.filter((line) => !line.includes(needle));
  if (kept.length === lines.length) throw new Error(`no line contains ${needle}`);
  return kept.join("\n");
}

/** Append one cron entry to `[triggers].crons`, comment and all. */
export function withCronLine(text: string, entry: string): string {
  const lines = text.split("\n");
  const start = lines.findIndex((line) => line.trim() === "[triggers]");
  if (start < 0) throw new Error("wrangler.toml has no [triggers] table");
  const close = lines.findIndex((line, index) => index > start && line.trim() === "]");
  if (close < 0) throw new Error("wrangler.toml [triggers] crons list is not closed");
  const last = lines[close - 1];
  // A comma belongs before the `# job-id` comment, or wrangler cannot parse it.
  const commentAt = last.indexOf("#");
  lines[close - 1] =
    commentAt >= 0
      ? `${last.slice(0, commentAt).replace(/,\s*$/, "")},${last.slice(commentAt)}`
      : `${last.replace(/,\s*$/, "")},`;
  lines.splice(close, 0, `  "${entry}", # added by the unrecognised-cron scenario`);
  return lines.join("\n");
}