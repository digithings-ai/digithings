import { describe, expect, it, vi } from "vitest";

vi.mock("../../chat/route", () => ({
  POST: vi.fn(),
  maxDuration: 120,
}));

import { POST as chatPost, maxDuration as chatMaxDuration } from "../../chat/route";
import { POST, maxDuration } from "./route";

describe("/api/v1/chat", () => {
  it("re-exports POST and maxDuration from /api/chat", () => {
    expect(POST).toBe(chatPost);
    expect(maxDuration).toBe(chatMaxDuration);
    expect(maxDuration).toBe(120);
  });
});
