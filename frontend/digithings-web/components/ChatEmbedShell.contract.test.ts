import { describe, it, expect } from "vitest";
import {
  DEFAULT_CHAT_EMBED_HOST,
  EMBED_READY_TIMEOUT_MS,
  OCC_CHAT_EMBED_HOST,
} from "@/components/ChatEmbedShell";

describe("ChatEmbedShell contracts", () => {
  it("keeps OCC as a virtual host distinct from the digithings parent", () => {
    expect(DEFAULT_CHAT_EMBED_HOST).toBe("digithings.ai");
    expect(OCC_CHAT_EMBED_HOST).toBe("occ.digithings.ai");
    expect(OCC_CHAT_EMBED_HOST).not.toBe(DEFAULT_CHAT_EMBED_HOST);
  });

  it("allows cold-start before treating a missing ready as a load failure", () => {
    expect(EMBED_READY_TIMEOUT_MS).toBeGreaterThanOrEqual(30_000);
  });
});
