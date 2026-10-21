import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Pins the one-loading-affordance rule.
 *
 * Before the agent answers, the chat shows a single loading row: the dot
 * matrix on its own, with the phase text only when we know it (waking up
 * services, connecting, warming up). The moment anything real arrives —
 * reasoning, a tool call, the answer — the work block takes over and the
 * loading row is gone. The two must never stack: a "Working" block above a
 * second animation below reads as two things happening at once.
 */
const here = dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

describe("one loading affordance per turn", () => {
  it("retires the loading row as soon as anything real arrived", () => {
    const thread = read("gallery-thread/thread.aui.tsx");
    // The gate is "any part that is not a status part": a connection or
    // status part is the pre-response phase, not content.
    expect(thread).toMatch(
      /const hasContent = messageParts\.some\(\(part\) => part\.type !== "data"\)/,
    );
    expect(thread).toMatch(
      /return hasContent \? null : <AssistantWorkingIndicator \/>/,
    );
  });

  it("no work block before the model has produced anything", () => {
    const thread = read("gallery-thread/thread.aui.tsx");
    // A status part is not work: the chain header must not appear while the
    // only thing in the group is the connection state.
    expect(thread).toMatch(/const holdsWork = part\.indices\.some/);
    expect(thread).toMatch(/if \(!holdsWork\) return <>\{children\}<\/>;/);
  });

  it("keeps the phase copy for the pre-response phase", () => {
    const thread = read("gallery-thread/thread.aui.tsx");
    expect(thread).toMatch(/Waking up services…/);
    expect(thread).toMatch(/Connecting…/);
    expect(thread).toMatch(/Warming up…/);
  });

  it("the work block is the only animation once the agent works", () => {
    const chain = read("gallery-thread/work-chain.tsx");
    // The chain header carries the running marker; the rows inside it carry
    // their own. Nothing else animates in the message area.
    expect(chain).toMatch(/aui_work-chain-trigger/);
  });
});
