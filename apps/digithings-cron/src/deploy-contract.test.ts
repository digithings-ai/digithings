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
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { DurableObject } from "cloudflare:workers";
import { BackfillLedger } from "./backfill-do";
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


/**
 * Every class the Worker deploys, by class name: the file that declares it
 * and that file's source.
 */
function declaredClasses(): Map<string, { file: string; source: string }> {
  const out = new Map<string, { file: string; source: string }>();
  for (const file of readdirSync(resolve(process.cwd(), "src"))) {
    if (!file.endsWith(".ts") || file.endsWith(".test.ts")) continue;
    const source = readFileSync(resolve(process.cwd(), "src", file), "utf8");
    for (const match of source.matchAll(/export class (\w+)/g)) {
      out.set(match[1], { file, source });
    }
  }
  return out;
}

/** The class names every `new_sqlite_classes` migration creates. */
function sqliteClasses(): string[] {
  const names: string[] = [];
  for (const block of blocks("[[migrations]]")) {
    const match = block.match(/new_sqlite_classes\s*=\s*\[([^\]]*)\]/);
    if (!match) continue;
    for (const name of match[1].matchAll(/"([^"]+)"/g)) names.push(name[1]);
  }
  return names;
}

/**
 * A Durable Object class that does not extend `DurableObject` has no callable
 * methods on its stub, and the runtime refuses the call with "The receiving
 * Durable Object does not support RPC, because its class was not declared with
 * `extends DurableObject`". The claim path then fails open on every tick and
 * the dedupe never runs - with every unit test green, because the tests call
 * the class directly and never through a stub.
 *
 * So the contract is pinned here, against the real `wrangler.toml` and the real
 * class sources: a class the deploy creates as SQLite-backed must be
 * RPC-capable. This is the check whose absence let DIG-4384 ship a Worker
 * whose dedupe guard was inert from its first deploy.
 */
describe("Durable Object classes are RPC-capable (DIG-4516)", () => {
  it("declares every SQLite-backed Durable Object class as `extends DurableObject`", () => {
    const classes = declaredClasses();
    const names = sqliteClasses();
    expect(names.length).toBeGreaterThan(0);
    for (const name of names) {
      const found = classes.get(name);
      expect(found, `${name} is not declared in src/`).toBeDefined();
      expect(
        found!.source,
        `${name} must extend DurableObject to be callable over RPC`,
      ).toMatch(new RegExp(`export class ${name} extends DurableObject\\b`));
      expect(
        found!.source,
        `${name} must import DurableObject from "cloudflare:workers"`,
      ).toMatch(/import \{[^}]*DurableObject[^}]*\} from "cloudflare:workers"/);
    }
  });

  it("gives the deployed classes the RPC-capable prototype chain", () => {
    for (const [name, value] of [
      ["StartCounter", StartCounter],
      ["BackfillLedger", BackfillLedger],
    ] as const) {
      expect(
        value.prototype,
        `${name} must inherit from DurableObject`,
      ).toBeInstanceOf(DurableObject);
    }
  });
});
