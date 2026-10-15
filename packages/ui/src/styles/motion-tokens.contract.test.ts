import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// `packages/design/motion.json` is the one source of motion timing (ADR D6,
// docs/surfaces/adr-surfaces-1-0.md). tokens.css hand-writes the CSS view of
// it; this pins the two together. The `linear()` spring twin inside
// `@supports` is a rendering of `ease.house`, not a token, so it is skipped.
const here = __dirname;
const designDir = path.resolve(here, "../../../design");

type Motion = {
  ease: { house: [number, number, number, number] };
  duration: Record<string, number>;
  frame: Record<string, number>;
  reduced: { duration: number; frame: null };
};

const motion = JSON.parse(readFileSync(path.join(designDir, "motion.json"), "utf8")) as Motion;
const tokens = readFileSync(path.join(designDir, "tokens.css"), "utf8");
const plain = tokens.replace(/@supports[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}/g, "");

function seconds(value: string): number {
  const match = /^([\d.]+)(ms|s)$/.exec(value.trim());
  if (!match) throw new Error(`not a time: ${value}`);
  const n = Number(match[1]);
  return Math.round(match[2] === "s" ? n * 1000 : n);
}

function bezier(value: string): number[] {
  const match = /^cubic-bezier\(([^)]*)\)$/.exec(value.trim());
  if (!match) throw new Error(`not a cubic-bezier: ${value}`);
  return match[1].split(",").map((part) => Number(part.trim()));
}

describe("motion.json shape", () => {
  it("uses integer milliseconds and a bezier 4-tuple", () => {
    expect(motion.ease.house).toHaveLength(4);
    for (const group of [motion.duration, motion.frame]) {
      for (const [name, ms] of Object.entries(group)) {
        expect(Number.isInteger(ms), name).toBe(true);
        expect(ms, name).toBeGreaterThan(0);
      }
    }
    expect(motion.reduced).toEqual({ duration: 0, frame: null });
  });
});

describe("tokens.css mirrors motion.json", () => {
  it("declares exactly one --duration-* per motion.json duration, equal in ms", () => {
    const declared = new Map<string, number>();
    for (const m of plain.matchAll(/--duration-([a-z-]+)\s*:\s*([^;]+);/g)) {
      const name = m[1];
      const ms = seconds(m[2]);
      if (declared.has(name)) expect(declared.get(name), `--duration-${name}`).toBe(ms);
      declared.set(name, ms);
    }
    expect(Object.fromEntries(declared)).toEqual(motion.duration);
  });

  it("sets --ease and --ease-glide to ease.house", () => {
    const eases = [...plain.matchAll(/--(ease|ease-glide)\s*:\s*([^;]+);/g)];
    expect(eases.map((m) => m[1]).sort()).toEqual(["ease", "ease-glide"]);
    for (const m of eases) expect(bezier(m[2]), `--${m[1]}`).toEqual(motion.ease.house);
  });
});
