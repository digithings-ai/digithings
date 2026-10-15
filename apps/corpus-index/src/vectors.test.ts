import { describe, expect, it } from "vitest";
import { EMBED_DIMENSIONS, EMBED_MODEL_ID } from "./model";
import { buildTicketVectors, idsToDrop } from "./vectors";

function embed(texts: string[]): number[][] {
  return texts.map(() => Array.from({ length: EMBED_DIMENSIONS }, () => 0.1));
}

describe("buildTicketVectors", () => {
  const ticket = {
    id: 42,
    title: "Portal reset",
    state: "closed",
    group: "support",
    created_at: "2026-10-01T00:00:00.000Z",
    updated_at: "2026-10-13T00:00:00.000Z",
    customer: "Jane Doe",
    customer_name: "Jane Doe",
    owner: "Alex Agent",
  };

  it("masks identity, skips internal articles, and keeps a closed ticket", async () => {
    const vectors = await buildTicketVectors(
      ticket,
      [
        {
          id: 7,
          body: "From: Jane Doe <jane@example.com>\nPlease call +49 30 12345678 about DE89370400440532013000. Copy ops@example.com.",
          content_type: "text/plain",
          from: "Jane Doe <jane@example.com>",
        },
        { id: 8, body: "internal note with secret@example.com", internal: true },
      ],
      "https://support.example",
      embed,
    );
    expect(vectors).toHaveLength(1);
    expect(vectors[0].id).toBe("t42-a7-c0");
    const meta = vectors[0].metadata;
    expect(meta.model).toBe(EMBED_MODEL_ID);
    expect(meta.state).toBe("closed");
    expect(JSON.stringify(meta)).not.toMatch(/jane@example.com|Jane|\+49|DE89|customer|from|owner/i);
    expect(String(meta.content)).toContain("[email]");
    expect(String(meta.content)).toContain("[phone]");
    expect(String(meta.content)).toContain("[iban]");
    expect(meta.url).toBe("https://support.example/#ticket/zoom/42");
  });

  it("reconcile drops ids that are no longer live", () => {
    expect(idsToDrop(["1", "2", "3"], ["2"])).toEqual(["1", "3"]);
  });
});
