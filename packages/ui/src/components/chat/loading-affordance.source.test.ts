import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Pins the one-loading-affordance rule.
 *
 * Before the agent answers, the chat shows a single loading row: the dot
 * matrix on its own, with status text only when the server sent a status
 * message (waking up services, waiting for capacity). The moment anything real arrives —
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
    // Shared with the base skins (`trace-grouping/chain-state.ts`).
    expect(read("trace-grouping/chain-state.ts")).toMatch(
      /parts\.some\(\(part\) => part !== undefined && part\.type !== "data"\)/,
    );
    for (const file of [thread, read("skins/base/thread.tsx")]) {
      expect(file).toMatch(/const hasContent = messageHasContent\(messageParts\)/);
      expect(file).toMatch(/return hasContent \? null : <AssistantWorkingIndicator \/>/);
    }
  });

  it("no work block before the model has produced anything", () => {
    const thread = read("gallery-thread/thread.aui.tsx");
    // A status part is not work: the chain header must not appear while the
    // only thing in the group is the connection state.
    expect(thread).toMatch(/const holdsWork = chainHoldsWork\(messageParts, part\.indices\)/);
    expect(thread).toMatch(/if \(!holdsWork\) return <>\{children\}<\/>;/);
    expect(read("skins/base/thread.tsx")).toMatch(
      /if \(!chainHoldsWork\(messageParts, part\.indices\)\) return <>\{children\}<\/>;/,
    );
  });

  it("shows status text only when the server sent one", () => {
    // DIG-4459: a bare wait is the animation alone. The text comes from the
    // connection part's message (or the warm-up probe), never a client
    // default.
    for (const rel of ["gallery-thread/thread.aui.tsx", "skins/base/thread.tsx"]) {
      const thread = read(rel);
      expect(thread).toMatch(/connectionStatusText\(s\.message\.parts\)/);
      expect(thread).not.toMatch(/Connecting…|"Connecting"|Warming up…/);
    }
  });

  it("the work block is the only animation once the agent works", () => {
    const chain = read("gallery-thread/work-chain.tsx");
    // The chain header carries the running marker; the rows inside it carry
    // their own. Nothing else animates in the message area.
    expect(chain).toMatch(/aui_work-chain-trigger/);
  });
});
