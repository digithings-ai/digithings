import { describe, expect, it } from "vitest";
import {
  buildGatedMessage,
  isUnlockedMessage,
  MAX_GATED_QUESTION_CHARS,
  UNLOCKED_MESSAGE_TYPE,
} from "@/lib/embed-trial-messages";

const parent = "https://datatap.stream";
const ev = (origin: string, data: unknown) => ({ origin, data }) as MessageEvent;

describe("isUnlockedMessage", () => {
  it("accepts the unlock type only from the exact parent origin", () => {
    expect(isUnlockedMessage(ev(parent, { type: UNLOCKED_MESSAGE_TYPE }), parent)).toBe(true);
  });
  it("rejects a wrong origin", () => {
    expect(isUnlockedMessage(ev("https://evil.example", { type: UNLOCKED_MESSAGE_TYPE }), parent)).toBe(false);
  });
  it("rejects a wrong type", () => {
    expect(isUnlockedMessage(ev(parent, { type: "datatap:gated" }), parent)).toBe(false);
  });
  it("rejects when the parent origin is unknown", () => {
    expect(isUnlockedMessage(ev(parent, { type: UNLOCKED_MESSAGE_TYPE }), undefined)).toBe(false);
  });
});

const msg = (role: string, content: string) => ({ role, content });

describe("buildGatedMessage", () => {
  it("carries the session id and the first 3 user questions in order", () => {
    expect(
      buildGatedMessage("sess-1", [
        msg("user", "q1"),
        msg("assistant", "a1"),
        msg("user", "q2"),
        msg("assistant", "a2"),
        msg("user", "q3"),
        msg("user", "q4"),
      ]),
    ).toEqual({ type: "datatap:gated", sessionId: "sess-1", questions: ["q1", "q2", "q3"] });
  });

  it("omits absent fields rather than sending empty ones", () => {
    expect(buildGatedMessage(null, [])).toEqual({ type: "datatap:gated" });
  });

  it("truncates an over-long question and session id", () => {
    const long = "x".repeat(MAX_GATED_QUESTION_CHARS + 50);
    const out = buildGatedMessage("y".repeat(300), [msg("user", long)]);
    expect(out.questions?.[0]).toHaveLength(MAX_GATED_QUESTION_CHARS);
    expect(out.sessionId).toHaveLength(200);
  });

  it("skips blank user turns", () => {
    expect(
      buildGatedMessage(null, [msg("user", "  "), msg("user", "q1")]).questions,
    ).toEqual(["q1"]);
  });
});
