import { describe, expect, it } from "vitest";

import {
  EMBED_FREE_TURN_LIMIT,
  EMBED_TRIAL_TURN_LIMIT,
  formatEmbedTurnCounter,
} from "@/lib/embed-turn-limits";

describe("formatEmbedTurnCounter", () => {
  it("counts free turns UP from 0, matching the old trial flow", () => {
    expect(formatEmbedTurnCounter(0, EMBED_FREE_TURN_LIMIT)).toBe("0/3");
    expect(formatEmbedTurnCounter(1, EMBED_FREE_TURN_LIMIT)).toBe("1/3");
    expect(formatEmbedTurnCounter(2, EMBED_FREE_TURN_LIMIT)).toBe("2/3");
    expect(formatEmbedTurnCounter(3, EMBED_FREE_TURN_LIMIT)).toBe("3/3");
  });

  it("uses the raised trial quota after unlock", () => {
    expect(formatEmbedTurnCounter(0, EMBED_TRIAL_TURN_LIMIT)).toBe("0/100");
    expect(formatEmbedTurnCounter(37, EMBED_TRIAL_TURN_LIMIT)).toBe("37/100");
  });

  it("never reports a negative or over-limit usage", () => {
    expect(formatEmbedTurnCounter(-2, EMBED_FREE_TURN_LIMIT)).toBe("0/3");
    expect(formatEmbedTurnCounter(5, EMBED_FREE_TURN_LIMIT)).toBe("3/3");
    expect(formatEmbedTurnCounter(140, EMBED_TRIAL_TURN_LIMIT)).toBe("100/100");
  });
});
