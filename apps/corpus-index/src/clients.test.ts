import { describe, expect, it } from "vitest";
import { createEmbedder, createTicketSource, createVectorStore } from "./clients";
import { EMBED_DIMENSIONS, EMBED_MODEL_ID } from "./model";

describe("createTicketSource", () => {
  it("fails with a status code and does not echo the body or the token", async () => {
    const secret = "zammad-token-value";
    const source = createTicketSource(
      () => secret,
      async (_url, init) => {
        const headers = new Headers(init?.headers);
        expect(headers.get("Authorization")).toBe(`Token token=${secret}`);
        return new Response("jane@example.com and the token", { status: 500 });
      },
    );
    await expect(source.search("https://support.example", "id:>0", 1)).rejects.toThrow(
      "zammad_http_500",
    );
    await expect(source.search("https://support.example", "id:>0", 1)).rejects.toThrow(
      /^zammad_http_500$/,
    );
  });

  it("reads a tickets envelope and rejects an unexpected payload without echoing it", async () => {
    const source = createTicketSource(
      () => "t",
      async () => Response.json({ tickets: [{ id: 4, title: "Portal" }] }),
    );
    const rows = await source.search("https://support.example", "id:>0", 1);
    expect(rows.map((row) => row.id)).toEqual([4]);
    const broken = createTicketSource(
      () => "t",
      async () => Response.json({ assets: { customer: "jane@example.com" } }),
    );
    await expect(broken.search("https://support.example", "id:>0", 1)).rejects.toThrow(
      /^zammad_payload$/,
    );
  });

  it("names a missing token without a value", async () => {
    const source = createTicketSource(() => "");
    await expect(source.search("https://support.example", "id:>0", 1)).rejects.toThrow(
      "zammad_token_missing",
    );
  });
});

describe("createVectorStore", () => {
  it("does not echo a failed response body", async () => {
    const store = createVectorStore("account", () => "cf-token", async () => {
      return new Response("index occ secret", { status: 403 });
    });
    await expect(
      store.deleteIds("tickets-m3", ["t1-a1-c0"]),
    ).rejects.toThrow(/^vectorize_http_403$/);
  });
});

describe("createEmbedder", () => {
  it("calls bge-m3 and rejects a short vector", async () => {
    const models: string[] = [];
    const embedder = createEmbedder({
      run: async (model, input) => {
        models.push(model);
        return { data: input.text.map(() => [0.1]) };
      },
    });
    await expect(embedder.embed(["hallo"])).rejects.toThrow("embed_dimensions");
    expect(models).toEqual([EMBED_MODEL_ID]);
    const ok = createEmbedder({
      run: async (_model, input) => ({
        data: input.text.map(() => Array.from({ length: EMBED_DIMENSIONS }, () => 0.1)),
      }),
    });
    const vectors = await ok.embed(["hello", "hallo"]);
    expect(vectors).toHaveLength(2);
    expect(vectors[0]).toHaveLength(EMBED_DIMENSIONS);
  });
});
