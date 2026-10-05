/**
 * Every enabled job.cron must appear in wrangler.toml [triggers] crons.
 *
 * jobs.ts asserts the parity in a comment, and jobs.test.ts pins the list of
 * uniqueEnabledCrons(), but nothing compared either to wrangler.toml. So a new
 * job could be added to jobs.ts and simply never fire: Cloudflare would never
 * invoke the Worker for that cron, the dispatch would never happen, and the
 * absence would look exactly like "the check passed". That is DIG-1073's
 * failure mode reached by a different route, which is why it gets a test here
 * rather than a comment.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { uniqueEnabledCrons } from "./jobs";

const WRANGLER = new URL("../wrangler.toml", import.meta.url);

function wranglerCrons(): string[] {
  const text = readFileSync(WRANGLER, "utf8");
  // Match the table header at the start of a line, not the phrase inside the
  // header comment — which mentions "[triggers] crons" and would otherwise hand
  // back the top of the file (name, account_id, ...) as if it were crons.
  const header = /^\s*\[triggers\]\s*$/m.exec(text);
  expect(header, "wrangler.toml has no [triggers] table").not.toBeNull();
  const rest = text.slice(header!.index + header![0].length);
  const list = rest.slice(0, rest.indexOf("]"));
  return Array.from(list.matchAll(/"([^"]+)"/g)).map((m) => m[1]);
}

describe("wrangler [triggers] crons", () => {
  it("lists every unique enabled job cron", () => {
    const fromJobs = uniqueEnabledCrons();
    const fromWrangler = wranglerCrons();
    for (const cron of fromJobs) {
      expect(fromWrangler, `wrangler.toml is missing cron "${cron}"`).toContain(cron);
    }
  });

  it("lists no cron that no enabled job claims", () => {
    // The other direction matters too: a stale wrangler cron fires the Worker
    // on a schedule with nothing to run, which index.ts reports as
    // unmapped_cron and logs as an error — noise that trains people to ignore
    // this log.
    const orphans = wranglerCrons().filter((cron) => !uniqueEnabledCrons().includes(cron));
    expect(orphans).toEqual([]);
  });

  it("agrees with uniqueEnabledCrons() exactly, in order", () => {
    expect(wranglerCrons()).toEqual(uniqueEnabledCrons());
  });
});