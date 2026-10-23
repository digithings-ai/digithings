import { describe, expect, test } from "bun:test";

import { createClock } from "../src/clock";

describe("pausable banner clock", () => {
  test("counts the time it spends running", () => {
    const clock = createClock(1000);
    expect(clock.elapsed(1040)).toBe(40);
    expect(clock.elapsed(1100)).toBe(100);
    expect(clock.paused).toBe(false);
  });

  test("freezes while paused and resumes where it stopped", () => {
    const clock = createClock(0);
    expect(clock.elapsed(500)).toBe(500);
    clock.pause(500);
    expect(clock.paused).toBe(true);
    expect(clock.elapsed(9000)).toBe(500);
    clock.resume(9000);
    expect(clock.elapsed(9040)).toBe(540);
  });

  test("pausing twice does not bank the same span twice", () => {
    const clock = createClock(0);
    clock.elapsed(100);
    clock.pause(100);
    clock.pause(4000);
    clock.resume(4000);
    expect(clock.elapsed(4100)).toBe(200);
  });

  test("resuming a running clock loses no time", () => {
    const clock = createClock(0);
    expect(clock.elapsed(100)).toBe(100);
    clock.resume(100);
    expect(clock.elapsed(150)).toBe(150);
  });

  test("ignores a clock that goes backwards", () => {
    const clock = createClock(1000);
    expect(clock.elapsed(900)).toBe(0);
    expect(clock.elapsed(1000)).toBe(0);
    expect(clock.elapsed(1040)).toBe(40);
  });
});
