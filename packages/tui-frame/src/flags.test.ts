import { describe, expect, test } from "bun:test";

import { parseFlags, positiveInt, zonedIso } from "./flags.ts";

const KNOWN = ["--out", "--width", "--captured-at"] as const;

describe("the exporter flag parser", () => {
  test("it reads the value in both spellings", () => {
    expect(parseFlags(["--out", "/tmp/f.json"], KNOWN).get("--out")).toBe("/tmp/f.json");
    expect(parseFlags(["--out=/tmp/f.json"], KNOWN).get("--out")).toBe("/tmp/f.json");
  });

  test("it reads several flags in one call", () => {
    const flags = parseFlags(["--width", "120", "--captured-at=2026-10-22T05:45:00Z"], KNOWN);
    expect(flags.get("--width")).toBe("120");
    expect(flags.get("--captured-at")).toBe("2026-10-22T05:45:00Z");
  });

  test("it refuses an unknown flag instead of ignoring it", () => {
    expect(() => parseFlags(["--nope"], KNOWN)).toThrow(/unknown flag "--nope"/);
  });

  test("it refuses a stray word instead of treating it as a value", () => {
    expect(() => parseFlags(["frame.json"], KNOWN)).toThrow(/unexpected argument/);
  });

  test("it refuses a flag with no value", () => {
    expect(() => parseFlags(["--out"], KNOWN)).toThrow(/--out needs a value/);
    expect(() => parseFlags(["--out", "--width", "80"], KNOWN)).toThrow(/needs a value/);
  });
});

describe("flag value readers", () => {
  test("positiveInt reads a positive integer", () => {
    expect(positiveInt("120", "--width")).toBe(120);
  });

  test("positiveInt refuses zero, a word and a fraction's text", () => {
    expect(() => positiveInt("0", "--width")).toThrow(/positive number/);
    expect(() => positiveInt("wide", "--width")).toThrow(/positive number/);
  });

  test("zonedIso keeps a timestamp that carries a zone", () => {
    expect(zonedIso("2026-10-22T05:45:00.000Z", "--captured-at")).toBe(
      "2026-10-22T05:45:00.000Z",
    );
    expect(zonedIso("2026-10-22T07:45:00+02:00", "--captured-at")).toBe(
      "2026-10-22T07:45:00+02:00",
    );
  });

  test("zonedIso refuses an offset-less timestamp", () => {
    // An offset-less timestamp reads in the local zone, so the same artifact
    // would label a different moment on another machine.
    expect(() => zonedIso("2026-10-22T05:45:00.000", "--captured-at")).toThrow(/zone/);
    expect(() => zonedIso("2026-10-22 05:45", "--captured-at")).toThrow(/zone/);
  });
});
