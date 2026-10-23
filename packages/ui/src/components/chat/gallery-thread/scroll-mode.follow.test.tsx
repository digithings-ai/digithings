// @vitest-environment jsdom
import { render } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useFollowStream } from "./scroll-mode";

/** Every ResizeObserver callback registered during the test. */
let resizes: Array<() => void> = [];
/** Frame callbacks queued by the hook; flushed on demand, like a browser. */
let frames: FrameRequestCallback[] = [];

function flushFrames(): void {
  const queued = frames;
  frames = [];
  queued.forEach((cb) => cb(0));
}

class FakeResizeObserver {
  constructor(private readonly cb: () => void) {
    resizes.push(cb);
  }
  observe(): void {}
  disconnect(): void {}
  unobserve(): void {}
}

function Probe({
  enabled,
  resumeKey = 0,
  onElement,
}: {
  enabled: boolean;
  resumeKey?: number;
  onElement: (el: HTMLElement) => void;
}) {
  const [el, setEl] = useState<HTMLElement | null>(null);
  useFollowStream(el, enabled, resumeKey);
  return (
    <div
      data-testid="viewport"
      ref={(node) => {
        if (!node) return;
        setEl(node);
        onElement(node);
      }}
    />
  );
}

function makeViewport(scrollHeight: number, clientHeight: number, scrollTop: number): HTMLElement {
  const el = document.createElement("div");
  Object.defineProperty(el, "scrollHeight", { configurable: true, get: () => scrollHeight });
  Object.defineProperty(el, "clientHeight", { configurable: true, get: () => clientHeight });
  el.scrollTop = scrollTop;
  return el;
}

function grow(el: HTMLElement, scrollHeight: number): void {
  Object.defineProperty(el, "scrollHeight", { configurable: true, get: () => scrollHeight });
  resizes.forEach((cb) => cb());
  flushFrames();
}

describe("useFollowStream", () => {
  beforeEach(() => {
    resizes = [];
    frames = [];
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      frames.push(cb);
      return frames.length;
    });
    vi.stubGlobal("cancelAnimationFrame", () => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("chases the bottom when the content grows", () => {
    let el: HTMLElement | null = null;
    render(<Probe enabled onElement={(node) => (el = node)} />);
    const real = el as unknown as HTMLElement;
    Object.defineProperty(real, "scrollHeight", { configurable: true, get: () => 1000 });
    Object.defineProperty(real, "clientHeight", { configurable: true, get: () => 300 });
    real.scrollTop = 600; // 100px short of the bottom
    grow(real, 1200);
    expect(real.scrollTop).toBe(1200);
  });

  it("stops chasing after the reader scrolls up", () => {
    let el: HTMLElement | null = null;
    render(<Probe enabled onElement={(node) => (el = node)} />);
    const real = el as unknown as HTMLElement;
    Object.defineProperty(real, "scrollHeight", { configurable: true, get: () => 1000 });
    Object.defineProperty(real, "clientHeight", { configurable: true, get: () => 300 });
    real.scrollTop = 900; // at the bottom
    real.dispatchEvent(new Event("scroll"));

    real.scrollTop = 300; // the reader takes the scroll back
    real.dispatchEvent(new Event("scroll"));

    grow(real, 1400);
    expect(real.scrollTop).toBe(300);
  });

  it("resumes when the reader returns to the bottom", () => {
    let el: HTMLElement | null = null;
    render(<Probe enabled onElement={(node) => (el = node)} />);
    const real = el as unknown as HTMLElement;
    Object.defineProperty(real, "scrollHeight", { configurable: true, get: () => 1000 });
    Object.defineProperty(real, "clientHeight", { configurable: true, get: () => 300 });
    real.scrollTop = 900;
    real.dispatchEvent(new Event("scroll"));
    real.scrollTop = 300;
    real.dispatchEvent(new Event("scroll"));
    real.scrollTop = 700; // back at the bottom (1000 - 300)
    real.dispatchEvent(new Event("scroll"));

    grow(real, 1500);
    expect(real.scrollTop).toBe(1500);
  });

  it("does nothing in free mode", () => {
    let el: HTMLElement | null = null;
    render(<Probe enabled={false} onElement={(node) => (el = node)} />);
    const real = el as unknown as HTMLElement;
    Object.defineProperty(real, "scrollHeight", { configurable: true, get: () => 1000 });
    Object.defineProperty(real, "clientHeight", { configurable: true, get: () => 300 });
    real.scrollTop = 400;
    grow(real, 1600);
    expect(real.scrollTop).toBe(400);
  });

  it("resumes on the next send even while the reader is scrolled up", () => {
    let el: HTMLElement | null = null;
    const { rerender } = render(<Probe enabled resumeKey={1} onElement={(node) => (el = node)} />);
    const real = el as unknown as HTMLElement;
    Object.defineProperty(real, "scrollHeight", { configurable: true, get: () => 1000 });
    Object.defineProperty(real, "clientHeight", { configurable: true, get: () => 300 });
    real.scrollTop = 900;
    real.dispatchEvent(new Event("scroll"));
    real.scrollTop = 300;
    real.dispatchEvent(new Event("scroll"));

    grow(real, 1400);
    expect(real.scrollTop).toBe(300);

    // A new user message bumps the key: the send is intent to read the answer.
    rerender(<Probe enabled resumeKey={2} onElement={(node) => (el = node)} />);
    grow(real, 1600);
    expect(real.scrollTop).toBe(1600);
  });
});
