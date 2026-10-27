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

  it("names the core Supabase project, and keeps the key a secret", () => {
    expect(toml).toContain('SUPABASE_URL = "https://rwagjbkvxkdwqmouagad.supabase.co"');
    expect(toml).toContain("CORE_SUPABASE_SERVICE_KEY");
    expect(toml).not.toMatch(/^CORE_SUPABASE_SERVICE_KEY\s*=/m);
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

  it("documents the secret name without a value", () => {
    const line = toml.split("\n").find((entry) => entry.includes("CORE_SUPABASE_SERVICE_KEY"));
    expect(line?.trim().startsWith("#")).toBe(true);
  });
});
