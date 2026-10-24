/**
 * A clock that can be paused. `elapsed` counts only time spent running, so a
 * banner stopped while its tab is hidden or its element is off screen picks up
 * at the moment it stopped instead of jumping to where the script would have
 * been. The animation itself stays a pure function of `elapsed`.
 */
export type Clock = {
  /** Running time up to `now`, in ms. */
  elapsed(now: number): number;
  /** Stop counting; time up to `now` is banked. Idempotent. */
  pause(now: number): void;
  /** Count again from `now`. Idempotent. */
  resume(now: number): void;
  readonly paused: boolean;
};

export function createClock(start: number): Clock {
  let spent = 0;
  let last = start;
  let paused = false;

  const step = (now: number) => {
    if (paused) return;
    const delta = now - last;
    if (delta <= 0) return;
    spent += delta;
    last = now;
  };

  return {
    elapsed(now) {
      step(now);
      return spent;
    },
    pause(now) {
      step(now);
      paused = true;
    },
    resume(now) {
      if (!paused) return;
      paused = false;
      last = now;
    },
    get paused() {
      return paused;
    },
  };
}
