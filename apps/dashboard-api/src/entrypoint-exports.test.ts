/**
 * The worker entrypoint must export `default` and nothing else.
 *
 * workerd builds its entrypoint map from EVERY top-level export of the
 * entrypoint module and throws
 *   Incorrect type for map entry '<name>': the provided value is not of
 *   type 'function or ExportedHandler'
 * for any value that is not a fetch handler or an ExportedHandler class. It
 * fails at module-eval time, so the worker never binds and nothing can reach
 * it — the whole service is down, with no route-level symptom to debug.
 *
 * That is the dashboard-api startup crash behind #4986 ("the chat service was
 * down, http://127.0.0.1:8788 refused"), which blocked the Brief desk.
 *
 * The invariant is pinned twice on purpose:
 *  1. over the real module namespace (what workerd actually reads), and
 *  2. over the source text, so a named export that a tree-shaker or a
 *     re-export would hide still fails the suite.
 *
 * Type-only exports (`export interface Env`, `export type X`) are erased at
 * runtime and are safe; they are allowed by check 2 and do not appear in the
 * runtime namespace of check 1.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import * as entrypoint from "./index";

const INDEX_PATH = fileURLToPath(new URL("./index.ts", import.meta.url));

describe("worker entrypoint surface", () => {
  it("exports `default` as the only runtime value (#4986)", () => {
    // A module-worker entrypoint may export only `default` (plus named
    // entrypoint classes). Anything else stops workerd from binding.
    expect(Object.keys(entrypoint).sort()).toEqual(["default"]);
  });

  it("`default` is a fetch handler", () => {
    const worker = (entrypoint as { default?: unknown }).default as { fetch?: unknown } | undefined;
    expect(typeof worker).toBe("object");
    expect(typeof worker?.fetch).toBe("function");
  });

  it("declares no value export other than `default`", () => {
    // Catches a re-export (`export { x } from "./y"`) and a class/const export
    // that could be hidden from the namespace by bundling.
    const source = readFileSync(INDEX_PATH, "utf8");
    const offenders = source
      .split("\n")
      .map((line, i) => ({ line, n: i + 1 }))
      .filter(({ line }) => /^export\s/.test(line))
      .filter(({ line }) => !/^export\s+(type|interface)\s/.test(line))
      .filter(({ line }) => !/^export\s+default\b/.test(line))
      .filter(({ line }) => !/^export\s*\{/.test(line));
    expect(offenders.map((o) => `line ${o.n}: ${o.line}`)).toEqual([]);
  });
});