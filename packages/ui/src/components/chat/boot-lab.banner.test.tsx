// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import * as React from "react";

// Test-env only: packages/hero-banner ships no tsconfig, so vitest compiles
// its JSX with the classic runtime while production (Next.js) uses automatic.
(globalThis as unknown as Record<string, unknown>).React ??= React;

/** Every set of props the banner branch handed the hero banner. */
const handed = vi.hoisted(() => [] as Array<{ replayLoading?: boolean }>);

vi.mock("@digithings/hero-banner/web", () => ({
  HeroBanner: (props: { replayLoading?: boolean }) => {
    handed.push(props);
    return <div data-testid="hero-banner" />;
  },
}));

import { BootLabOverlay, resolveBootLabVariant } from "./boot-lab";

afterEach(() => {
  cleanup();
  handed.length = 0;
  window.history.replaceState({}, "", "/");
  vi.unstubAllGlobals();
});

function stubMatchMedia(matches: (query: string) => boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: matches(query),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }));
}

const banner = () =>
  render(<BootLabOverlay variant="banner" ready={false} onSettled={() => {}} />);

describe("boot-lab banner variant", () => {
  it("is the default when nothing asks for a variant", () => {
    expect(resolveBootLabVariant(null)).toBe("banner");
    expect(resolveBootLabVariant(undefined)).toBe("banner");
  });

  it("still takes an explicit variant, from the prop or `?boot=`", () => {
    expect(resolveBootLabVariant("tooltask")).toBe("tooltask");
    expect(resolveBootLabVariant("dots")).toBe("dots");

    window.history.replaceState({}, "", "/?boot=scramble");
    expect(resolveBootLabVariant(null)).toBe("scramble");

    window.history.replaceState({}, "", "/?boot=banner");
    expect(resolveBootLabVariant(undefined)).toBe("banner");
  });

  it("falls back to the banner on an unknown value instead of the classic loader", () => {
    expect(resolveBootLabVariant("nope")).toBe("banner");
    window.history.replaceState({}, "", "/?boot=nope");
    expect(resolveBootLabVariant(null)).toBe("banner");
  });

  it("keeps `classic` as the opt-out to the pre-banner welcome loader", () => {
    expect(resolveBootLabVariant("classic")).toBeNull();
  });

  it("replays the banner's LOADING pass on mount", () => {
    stubMatchMedia(() => false);
    banner();
    expect(handed.length).toBeGreaterThan(0);
    expect(handed.every((props) => props.replayLoading === true)).toBe(true);
  });

  it("does not replay under reduced motion", () => {
    // The hook resolves motion after mount (hydration-safe), so the settled
    // props are the ones to read; HeroBanner itself also paints the settled
    // mark and starts no timer when the media query matches.
    stubMatchMedia((query) => query.includes("prefers-reduced-motion"));
    banner();
    expect(handed.length).toBeGreaterThan(0);
    expect(handed[handed.length - 1]?.replayLoading).toBe(false);
  });
});
