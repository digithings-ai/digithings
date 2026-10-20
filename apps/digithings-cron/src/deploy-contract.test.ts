/// <reference types="node" />
/**
 * The deploy half of the START_COUNTER contract (DIG-4384).
 *
 * A Durable Object binding, its migration and the class export are three facts
 * that no unit test on the claim path can see. Missing any one of them leaves
 * every test green and ships a Worker whose `scheduled()` runs with no counter,
 * silently back to two dispatches per tick. Deleting the binding even makes the
 * absent-binding test pass, because that test asserts the fail-open behaviour.
 *
 * So this file reads the real `wrangler.toml` at test time, the same way
 * `trigger-contract.test.ts` reads the real cron list, and imports the real
 * entrypoint export: the assertion of record is what the repo would deploy.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { StartCounter } from "./index";

// Resolved from the working directory because both entry points run the suite
// there (`npm run test --workspace digithings-cron` and
// `npm run check:deployed-triggers`). A run from the wrong directory fails
// loudly with ENOENT rather than passing on a fixture.
const WRANGLER_TOML = readFileSync(resolve(process.cwd(), "wrangler.toml"), "utf8");

/** Every array-of-tables block with `header`, as its field lines. */
function blocks(header: string): string[] {
  const out: string[] = [];
  let current: string[] | null = null;
  for (const line of WRANGLER_TOML.split("\n")) {
    if (/^\s*\[\[?.+?\]\]?\s*$/.test(line)) {
      if (current) out.push(current.join("\n"));
      current = line.trim() === header ? [] : null;
      continue;
    }
    current?.push(line);
  }
  if (current) out.push(current.join("\n"));
  return out;
}

describe("START_COUNTER deploy contract (DIG-4384)", () => {
  it("exports the StartCounter class from the Worker entrypoint", () => {
    // A type-only export satisfies tsc and fails `wrangler deploy` with
    // "not exported in your entrypoint file". Only a value passes this.
    expect(typeof StartCounter).toBe("function");
  });

  it("binds START_COUNTER to StartCounter", () => {
    const matches = blocks("[[durable_objects.bindings]]").filter((block) =>
      /^\s*name\s*=\s*"START_COUNTER"\s*$/m.test(block),
    );
    expect(matches).toHaveLength(1);
    expect(matches[0]).toMatch(/^\s*class_name\s*=\s*"StartCounter"\s*$/m);
  });

  it("creates StartCounter in migration v2, as a SQLite class", () => {
    const matches = blocks("[[migrations]]").filter((block) =>
      /^\s*tag\s*=\s*"v2"\s*$/m.test(block),
    );
    expect(matches).toHaveLength(1);
    expect(matches[0]).toMatch(/^\s*new_sqlite_classes\s*=\s*\[\s*"StartCounter"\s*\]\s*$/m);
  });

  it("does not declare StartCounter in an older migration tag", () => {
    const older = blocks("[[migrations]]").filter(
      (block) => !/^\s*tag\s*=\s*"v2"\s*$/m.test(block),
    );
    for (const block of older) expect(block).not.toContain("StartCounter");
  });
});
