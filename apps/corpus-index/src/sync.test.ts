import { describe, expect, it } from "vitest";
import { JOBS_KEY } from "./config";
import { EMBED_DIMENSIONS } from "./model";
import { syncDocs, syncTickets, sitemapLocs, type KvStore } from "./sync";

function memoryKv(): KvStore & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    get: async (key) => data.get(key) ?? null,
    put: async (key, value) => {
      data.set(key, value);
    },
    delete: async (key) => {
      data.delete(key);
    },
  };
}

const job = {
  id: "helpdesk",
  zammadBaseUrl: "https://support.example",
  siteUrl: "https://help.example",
  helpIndex: "help-m3",
  ticketsIndex: "tickets-m3",
  skipInternal: true,
};

function embed(texts: string[]): Promise<number[][]> {
  return Promise.resolve(texts.map(() => Array.from({ length: EMBED_DIMENSIONS }, () => 0.2)));
}

describe("syncTickets", () => {
  it("indexes a closed ticket, advances the cursor, and omits identity from the upsert", async () => {
    const kv = memoryKv();
    const upserts: { index: string; metadata: Record<string, string | number> }[] = [];
    const stats = await syncTickets(
      job,
      kv,
      {
        search: async (_base, query) => {
          expect(query).toContain("updated_at:>=");
          return [
            {
              id: 9,
              title: "Portal reset",
              state: "closed",
              group: "support",
              updated_at: "2026-10-13T01:00:00.000Z",
              customer: "Jane Doe",
            },
          ];
        },
        articles: async () => [
          { id: 3, body: "From: Jane Doe <jane@example.com>\nReset ops@example.com" },
        ],
        listIds: async () => ["9"],
      },
      {
        upsert: async (index, vectors) => {
          for (const vector of vectors) upserts.push({ index, metadata: vector.metadata });
        },
        deleteIds: async () => {},
      },
      { embed },
      new Date("2026-10-13T03:00:00.000Z"),
      false,
    );
    expect(stats.tickets).toBe(1);
    expect(stats.vectors).toBe(1);
    expect(upserts[0].index).toBe("tickets-m3");
    expect(JSON.stringify(upserts[0].metadata)).not.toMatch(/Jane|jane@example.com|ops@example.com/);
    expect(String(upserts[0].metadata.content)).toContain("[email]");
    expect(upserts[0].metadata.state).toBe("closed");
    expect(kv.data.get("corpus-index:cursor:helpdesk:tickets")).toBe("2026-10-13T01:00:00.000Z");
  });

  it("does not embed or write the cursor on a dry run", async () => {
    const kv = memoryKv();
    let embedded = 0;
    let writes = 0;
    await syncTickets(
      job,
      kv,
      {
        search: async () => [{ id: 1, state: "open", updated_at: "2026-10-13T01:00:00.000Z" }],
        articles: async () => [{ id: 1, body: "Hello" }],
        listIds: async () => [],
      },
      {
        upsert: async () => {
          writes += 1;
        },
        deleteIds: async () => {
          writes += 1;
        },
      },
      {
        embed: async () => {
          embedded += 1;
          return [];
        },
      },
      new Date("2026-10-13T03:00:00.000Z"),
      true,
    );
    expect(embedded).toBe(0);
    expect(writes).toBe(0);
    expect(kv.data.has("corpus-index:cursor:helpdesk:tickets")).toBe(false);
  });

  it("uses a 10 minute overlap on the next run", async () => {
    const kv = memoryKv();
    await kv.put("corpus-index:cursor:helpdesk:tickets", "2026-10-13T03:00:00.000Z");
    let seen = "";
    await syncTickets(
      job,
      kv,
      {
        search: async (_base, query) => {
          seen = query;
          return [];
        },
        articles: async () => [],
        listIds: async () => [],
      },
      { upsert: async () => {}, deleteIds: async () => {} },
      { embed },
      new Date("2026-10-14T03:00:00.000Z"),
      false,
    );
    expect(seen).toBe("updated_at:>=2026-10-13T02:50:00.000Z");
  });

  it("on Sunday deletes vectors for tickets that are gone", async () => {
    const kv = memoryKv();
    await kv.put("corpus-index:ticket-ids:helpdesk", JSON.stringify(["1", "2"]));
    await kv.put("corpus-index:vector-ids:helpdesk:1", JSON.stringify(["t1-a1-c0"]));
    const deleted: string[] = [];
    const stats = await syncTickets(
      job,
      kv,
      {
        search: async () => [],
        articles: async () => [],
        listIds: async () => ["2"],
      },
      {
        upsert: async () => {},
        deleteIds: async (_index, ids) => deleted.push(...ids),
      },
      { embed },
      new Date("2026-10-11T03:00:00.000Z"),
      false,
    );
    expect(stats.deleted).toBe(1);
    expect(deleted).toEqual(["t1-a1-c0"]);
  });
});

describe("syncDocs", () => {
  it("re-embeds a changed page and skips an unchanged one", async () => {
    const kv = memoryKv();
    const bodies: Record<string, string> = {
      "https://help.example/sitemap.xml":
        "<urlset><url><loc>https://help.example/a</loc></url><url><loc>https://help.example/b.pdf</loc></url></urlset>",
      "https://help.example/a": "<p>English help for the portal.</p>",
      "https://help.example/b.pdf": "not-text",
    };
    const upserts: string[] = [];
    const run = () =>
      syncDocs(
        job,
        kv,
        {
          fetchText: async (url) => ({
            ok: true,
            status: 200,
            contentType: url.endsWith(".pdf") ? "application/pdf" : "text/html",
            body: bodies[url] ?? "",
          }),
        },
        {
          upsert: async (_index, vectors) => upserts.push(...vectors.map((vector) => vector.id)),
          deleteIds: async () => {},
        },
        { embed },
        false,
      );
    const first = await run();
    expect(first.docs).toBe(1);
    expect(first.skipped).toBe(1);
    const second = await run();
    expect(second.docs).toBe(0);
    expect(upserts).toHaveLength(1);
  });

  it("reads sitemap locs", () => {
    expect(sitemapLocs("<loc>https://help.example/a</loc>")).toEqual(["https://help.example/a"]);
  });
});

describe("loadJobs", () => {
  it("returns nothing when KV has no job list", async () => {
    const kv = memoryKv();
    const { loadJobs } = await import("./sync");
    expect(await loadJobs(kv)).toEqual([]);
    await kv.put(JOBS_KEY, JSON.stringify([job]));
    expect(await loadJobs(kv)).toHaveLength(1);
  });
});
