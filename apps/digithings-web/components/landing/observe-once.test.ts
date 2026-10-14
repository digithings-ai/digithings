import { describe, expect, it, vi } from "vitest";

import { observeOnce } from "./observe-once";

type Callback = (entries: Pick<IntersectionObserverEntry, "isIntersecting">[]) => void;

function fakeObserver() {
  const state = { callback: null as Callback | null, disconnected: 0, observed: 0 };
  class Fake {
    constructor(callback: Callback) {
      state.callback = callback;
    }
    observe() {
      state.observed += 1;
    }
    disconnect() {
      state.disconnected += 1;
    }
  }
  return { state, Observer: Fake as unknown as typeof IntersectionObserver };
}

const target = {} as Element;

describe("observeOnce", () => {
  it("stays inert until the target intersects, then fires exactly once", () => {
    const { state, Observer } = fakeObserver();
    const onEnter = vi.fn();
    observeOnce(target, onEnter, 0.2, Observer);
    expect(state.observed).toBe(1);

    state.callback?.([{ isIntersecting: false }]);
    expect(onEnter).not.toHaveBeenCalled();

    state.callback?.([{ isIntersecting: true }]);
    state.callback?.([{ isIntersecting: true }]);
    expect(state.disconnected).toBeGreaterThanOrEqual(1);
    expect(onEnter).toHaveBeenCalledTimes(1);
  });

  it("fires immediately without IntersectionObserver", () => {
    const onEnter = vi.fn();
    observeOnce(target, onEnter, 0.2, undefined);
    expect(onEnter).toHaveBeenCalledTimes(1);
  });
});
