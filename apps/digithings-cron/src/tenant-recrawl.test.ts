import { describe, expect, it, vi } from "vitest";
import { runTenantRecrawlTick, type TenantDoc, type TenantDocReader } from "./tenant-recrawl";

const NOW = new Date("2026-10-26T07:30:00.000Z");
const DUE = "30 7 * * MON";

function doc(cron: string, url = "https://example.com/a", store = "store-a", index = "index-a"): TenantDoc {
  return { recrawl: { cron, targets: [{ url, store, index }] } };
}

function reader(docs: Record<string, TenantDoc | "throw">): TenantDocReader {
  return {
    async listIds() {
      return Object.keys(docs);
    },
    async read(id: string) {
      const row = docs[id];
      if (row === "throw") throw new Error(`read failed for ${id}`);
      return row;
    },
  };
}

describe("runTenantRecrawlTick", () => {
  it("runs a due tenant and skips a tenant that is not due", async () => {
    const tick = await runTenantRecrawlTick({
      now: NOW,
      reader: reader({
        "tenant-a": doc(DUE),
        "tenant-b": doc("30 7 * * TUE", "https://example.com/b", "store-b", "index-b"),
      }),
    });
    expect(tick.ran.map((row) => row.tenantId)).toEqual(["tenant-a"]);
    expect(tick.skipped).toContainEqual({ tenantId: "tenant-b", reason: "not_due" });
  });

  it("runs every tenant that is due on the same tick", async () => {
    const tick = await runTenantRecrawlTick({
      now: NOW,
      reader: reader({
        "tenant-a": doc(DUE),
        "tenant-b": doc(DUE, "https://example.com/b", "store-b", "index-b"),
      }),
    });
    expect(tick.ran.map((row) => row.tenantId)).toEqual(["tenant-a", "tenant-b"]);
  });

  it("skips a missing or empty recrawl block without throwing", async () => {
    const tick = await runTenantRecrawlTick({
      now: NOW,
      reader: reader({
        "tenant-a": {},
        "tenant-b": { recrawl: { cron: DUE, targets: [] } },
      }),
    });
    expect(tick.ran).toEqual([]);
    expect(tick.skipped).toEqual([
      { tenantId: "tenant-a", reason: "missing_recrawl" },
      { tenantId: "tenant-b", reason: "empty_targets" },
    ]);
  });

  it("skips and logs an invalid cron", async () => {
    const spy = vi.spyOn(console, "log").mockImplementation(() => {});
    const tick = await runTenantRecrawlTick({
      now: NOW,
      reader: reader({ "tenant-a": doc("not-a-cron") }),
    });
    expect(tick.ran).toEqual([]);
    expect(tick.skipped).toEqual([{ tenantId: "tenant-a", reason: "invalid_cron" }]);
    expect(spy.mock.calls.map((call) => String(call[0])).join("\n")).toContain("invalid_cron");
    spy.mockRestore();
  });

  it("passes store and index from the doc into the dry-run output", async () => {
    const tick = await runTenantRecrawlTick({
      now: NOW,
      reader: reader({ "tenant-a": doc(DUE, "https://example.com/docs", "store-a", "index-a") }),
    });
    expect(tick.ran).toEqual([
      {
        tenantId: "tenant-a",
        targets: [{ url: "https://example.com/docs", store: "store-a", index: "index-a" }],
      },
    ]);
  });

  it("dry-run is the default and does not call the write path", async () => {
    const write = vi.fn();
    const tick = await runTenantRecrawlTick({
      now: NOW,
      reader: reader({ "tenant-a": doc(DUE) }),
      writer: { write },
    });
    expect(tick.dryRun).toBe(true);
    expect(write).not.toHaveBeenCalled();
  });

  it("a reader error for one tenant does not stop the others", async () => {
    const tick = await runTenantRecrawlTick({
      now: NOW,
      reader: reader({
        "tenant-a": "throw",
        "tenant-b": doc(DUE, "https://example.com/b", "store-b", "index-b"),
      }),
    });
    expect(tick.skipped).toContainEqual({ tenantId: "tenant-a", reason: "reader_error" });
    expect(tick.ran.map((row) => row.tenantId)).toEqual(["tenant-b"]);
  });
});
