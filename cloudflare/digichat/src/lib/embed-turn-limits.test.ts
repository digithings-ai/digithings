import { describe, expect, it } from "vitest";

import {
  EMBED_FREE_TURN_LIMIT,
  EMBED_TRIAL_TURN_LIMIT,
  formatEmbedTurnCounter,
} from "@/lib/embed-turn-limits";

describe("formatEmbedTurnCounter", () => {
  it("counts down the free turns", () => {
    expect(formatEmbedTurnCounter(0, EMBED_FREE_TURN_LIMIT)).toBe(
      "3 of 3 free questions left",
    );
    expect(formatEmbedTurnCounter(1, EMBED_FREE_TURN_LIMIT)).toBe(
      "2 of 3 free questions left",
    );
    expect(formatEmbedTurnCounter(2, EMBED_FREE_TURN_LIMIT)).toBe(
      "1 of 3 free questions left",
    );
    expect(formatEmbedTurnCounter(3, EMBED_FREE_TURN_LIMIT)).toBe(
      "0 of 3 free questions left",
    );
  });

  it("labels the raised trial quota", () => {
    expect(formatEmbedTurnCounter(0, EMBED_TRIAL_TURN_LIMIT)).toBe(
      "100 of 100 trial questions left",
    );
    expect(formatEmbedTurnCounter(37, EMBED_TRIAL_TURN_LIMIT)).toBe(
      "63 of 100 trial questions left",
    );
  });

  it("never reports a negative remainder", () => {
    expect(formatEmbedTurnCounter(5, EMBED_FREE_TURN_LIMIT)).toBe(
      "0 of 3 free questions left",
    );
    expect(formatEmbedTurnCounter(140, EMBED_TRIAL_TURN_LIMIT)).toBe(
      "0 of 100 trial questions left",
    );
  });
});
