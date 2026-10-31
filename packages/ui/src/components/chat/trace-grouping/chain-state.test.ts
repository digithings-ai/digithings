import { describe, expect, it } from "vitest";
import {
  chainFollowedByText,
  chainHoldsWork,
  chainOpen,
  chainToolCount,
  messageHasContent,
  reasoningGroupDisclosure,
  toolGroupDisclosure,
} from "./chain-state";
import { effectiveToolStatus, resolveToolStatus, toolRowStatus } from "./tool-row";
import { createTraceT } from "../trace-i18n";
import { resolveWorkDisclosure } from "../stock/skin-types";

const parts = [
  { type: "reasoning" },
  { type: "tool-call" },
  { type: "source" },
  { type: "tool-call" },
  { type: "text", text: "answer" },
] as const;

describe("chain state", () => {
  it("counts tool calls, not the source parts between them", () => {
    expect(chainToolCount(parts, [1, 2, 3])).toBe(2);
    expect(chainHoldsWork(parts, [0, 1, 2, 3])).toBe(true);
    expect(chainHoldsWork([{ type: "source" }], [0])).toBe(false);
  });

  it("knows when an answer follows the chain", () => {
    expect(chainFollowedByText(parts, [0, 1, 2, 3])).toBe(true);
    expect(chainFollowedByText([{ type: "reasoning" }, { type: "text", text: "  " }], [0])).toBe(false);
  });

  it("treats status data parts as no content", () => {
    expect(messageHasContent([{ type: "data" }])).toBe(false);
    expect(messageHasContent([{ type: "data" }, { type: "reasoning" }])).toBe(true);
  });

  it("opens while working and folds once settled", () => {
    const base = { userOpen: null, openAtRest: false, foldOnAnswer: false };
    expect(chainOpen({ ...base, working: true, settled: false })).toBe(true);
    expect(chainOpen({ ...base, working: false, settled: true })).toBe(false);
    expect(chainOpen({ ...base, userOpen: true, working: false, settled: true })).toBe(true);
    expect(chainOpen({ userOpen: null, openAtRest: true, foldOnAnswer: false, working: false, settled: true })).toBe(true);
  });

  it("streams the groups open in the balanced view and pins them when locked", () => {
    const balanced = resolveWorkDisclosure("balanced");
    expect(toolGroupDisclosure(balanced, "collapsed", true).streamingOpen).toBe(true);
    expect(toolGroupDisclosure(balanced, "collapsed", false).streamingOpen).toBe(false);
    expect(reasoningGroupDisclosure(balanced, "locked_open", false)).toMatchObject({
      locked: true,
      defaultOpen: true,
    });
    const quiet = resolveWorkDisclosure("quiet");
    expect(toolGroupDisclosure(quiet, "collapsed", true).streamingOpen).toBe(false);
  });
});

describe("tool row", () => {
  it("reads a failed call as failed even when its part says complete", () => {
    const s = resolveToolStatus({ type: "complete" }, true, { error: "x" });
    expect(toolRowStatus(s).label).toBe("Failed tool");
  });

  it("reads a call left waiting by a stopped turn as cancelled", () => {
    const waiting = { type: "requires-action", reason: "tool-calls" } as const;
    expect(effectiveToolStatus(waiting, "stopped", false)).toEqual({ type: "incomplete", reason: "cancelled" });
    expect(effectiveToolStatus(waiting, "stopped", true)).toBe(waiting);
    expect(toolRowStatus({ type: "running" }, createTraceT("fr")).isRunning).toBe(true);
  });
});
