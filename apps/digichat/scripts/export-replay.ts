/**
 * Export a stored digichat conversation as one self-contained HTML replay.
 *
 *   npx tsx scripts/export-replay.ts --id <conversationId> --out ./replay.html
 *   npx tsx scripts/export-replay.ts --fixture --out ./replay.html
 *
 * `--id` calls a running digichat. The base URL is `--base` or `DIGICHAT_URL`
 * (default http://127.0.0.1:3000). Authorization is `--authorization`,
 * `DIGICHAT_REPLAY_AUTHORIZATION`, or `Bearer $DIGICHAT_API_KEY`.
 * `--fixture` builds the sample conversation on this machine and does not
 * call a model or a network.
 */
import { writeFileSync } from "node:fs";
import { buildReplayHtml, fixtureDocument } from "@digithings/ui/replay";
import { loadReplayStyles } from "@digithings/ui/replay/assets";
import { conversationReplayUrl, parseReplayCli, type ReplayCliPlan } from "../src/lib/replay-cli";

async function main(): Promise<void> {
  const parsed = parseReplayCli(process.argv.slice(2), process.env);
  if (!parsed.ok) {
    console.error(parsed.message);
    process.exitCode = 1;
    return;
  }
  const html = parsed.plan.mode === "fixture" ? fixtureHtml() : await fetchHtml(parsed.plan);
  if (html == null) {
    process.exitCode = 1;
    return;
  }
  if (parsed.plan.out) writeFileSync(parsed.plan.out, html);
  else process.stdout.write(html);
}

function fixtureHtml(): string {
  return buildReplayHtml(fixtureDocument(), loadReplayStyles());
}

async function fetchHtml(plan: Extract<ReplayCliPlan, { mode: "conversation" }>): Promise<string | null> {
  const url = conversationReplayUrl(plan);
  const headers = new Headers();
  if (plan.authorization) headers.set("authorization", plan.authorization);
  const res = await fetch(url, { headers });
  if (!res.ok) {
    const body = await res.text();
    console.error(`Replay export failed (${res.status}) ${url}`);
    if (body.trim()) console.error(body.slice(0, 500));
    return null;
  }
  return res.text();
}

void main();
