/**
 * The deployment contract, pinned.
 *
 * These are text assertions on `wrangler.toml` on purpose: the must-fix items of
 * the DIG-2664 review (`max_retries` and a dead-letter queue) live in that file,
 * not in the TypeScript, so nothing else in this suite can see them regress. The
 * same shape as the sibling Workers' env-pin tests.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const toml = readFileSync(new URL("../wrangler.toml", import.meta.url), "utf8");

/** The `[[queues.consumers]]` block, as its lines. */
function consumerBlock(): string[] {
  const lines = toml.split("\n");
  const start = lines.findIndex((line) => line.trim() === "[[queues.consumers]]");
  expect(start).toBeGreaterThanOrEqual(0);
  const out: string[] = [];
  for (const line of lines.slice(start + 1)) {
    if (line.trim().startsWith("[")) break;
    out.push(line);
  }
  return out;
}

describe("the queue retry contract", () => {
  it("sets max_retries explicitly, so a poison batch is bounded", () => {
    expect(consumerBlock().join("\n")).toMatch(/^max_retries = \d+$/m);
  });

  it("names the dead-letter queue", () => {
    expect(consumerBlock().join("\n")).toMatch(/^dead_letter_queue = "digitrace-ingest-dlq"$/m);
  });

  it("consumes the queue the producer sends to", () => {
    expect(toml).toMatch(/^queue = "digitrace-ingest"$/m);
  });

  it("binds a producer, so the receiver can enqueue", () => {
    expect(toml).toContain("[[queues.producers]]");
    expect(toml).toContain('binding = "INGEST_QUEUE"');
  });
});

describe("the bindings the code requires", () => {
  it("binds the archive bucket by the ADR's name", () => {
    expect(toml).toContain('bucket_name = "digitrace-archive"');
    expect(toml).toContain('binding = "ARCHIVE"');
  });

  it("binds the ingest-token namespace", () => {
    expect(toml).toContain("[[kv_namespaces]]");
    expect(toml).toContain('binding = "INGEST_TOKENS"');
  });

  it("binds the Analytics Engine dataset", () => {
    expect(toml).toContain("[[analytics_engine_datasets]]");
    expect(toml).toContain('binding = "ANALYTICS"');
    expect(toml).toContain('dataset = "digitrace_ingest"');
  });

  it("binds the D1 index and its migrations, not Supabase (DIG-2887 S1)", () => {
    expect(toml).toContain("[[d1_databases]]");
    expect(toml).toContain('binding = "INDEX_DB"');
    expect(toml).toContain('database_name = "digitrace"');
    expect(toml).toContain('migrations_dir = "migrations"');
    expect(toml).not.toMatch(/supabase/i);
  });
});

describe("the ingress surface", () => {
  it("keeps workers_dev off, so the route is the only entry point", () => {
    expect(toml).toMatch(/^workers_dev = false$/m);
  });

  it("keeps the custom-domain route a human step, commented out", () => {
    const routeLines = toml.split("\n").filter((line) => line.includes("trace.digithings.ai"));
    expect(routeLines.length).toBeGreaterThan(0);
    expect(routeLines.every((line) => line.trim().startsWith("#"))).toBe(true);
  });

  it("pins a compatibility date", () => {
    expect(toml).toMatch(/^compatibility_date = "\d{4}-\d{2}-\d{2}"$/m);
  });

  it("enables Workers Logs", () => {
    expect(toml).toContain("[observability]");
    expect(toml).toMatch(/^enabled = true$/m);
  });
});

describe("secrets stay out of the file", () => {
  it("carries no value that looks like a credential", () => {
    // A JWT-shaped service key, an sb_secret_ key, or a digi_live_ key.
    expect(toml).not.toMatch(/eyJ[A-Za-z0-9_-]{10,}/);
    expect(toml).not.toMatch(/sb_secret_[A-Za-z0-9_-]+/);
    expect(toml).not.toMatch(/digi_live_[A-Za-z0-9_-]+/);
  });

  it("needs no Worker secret: the D1 binding is the credential", () => {
    expect(toml).not.toMatch(/secret put/);
  });

  it("marks every placeholder id, so the deploy preflight can skip it", () => {
    const ids = toml.split("\n").filter((line) => /^(id|database_id) = "/.test(line));
    expect(ids.length).toBe(2);
    for (const line of ids) {
      if (/"0{8}-?0{4}-?0{4}-?0{4}-?0{12}"/.test(line)) {
        const at = toml.indexOf(line);
        expect(toml.slice(Math.max(0, at - 600), at)).toContain("PLACEHOLDER");
      }
    }
  });
});
