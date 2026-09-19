// @vitest-environment happy-dom
/**
 * TabStrip ink re-measure on a `dir` flip (#4306, canon audit S1).
 *
 * The reference `/rtl` proof caught the sliding `.tab-ink` keeping its LTR
 * offset (~372px from the active tab) after the page flipped to RTL, until the
 * user clicked a tab — nothing re-ran the measurement, and a window `resize`
 * never fires for a direction change. The component now observes `<html>`'s
 * `dir` (MutationObserver) plus the strip's and tabs' boxes (ResizeObserver)
 * and re-measures. This is the DOM half: flip the document direction with no
 * click and assert the ink's transform is recomputed with the RTL mirror.
 *
 * happy-dom does not lay out, so `getBoundingClientRect` is stubbed with a
 * deterministic box per element; the point is that `position()` runs again and
 * reads the (now RTL) direction, not that a real browser computed pixels.
 */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { TabStrip, type TabItem } from "./TabStrip";

const TABS: TabItem[] = [
  { id: "one", label: "One" },
  { id: "two", label: "Two" },
];

beforeAll(() => {
  (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(() => {
  document.documentElement.removeAttribute("dir");
  document.body.replaceChildren();
});

async function mount(ui: React.ReactElement) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(ui);
  });
  return async () => {
    await act(async () => root.unmount());
    host.remove();
  };
}

/** Deterministic boxes: the strip spans 0..300; tab 0 sits at 10..100. */
function stubRects(list: HTMLElement) {
  const orig = Element.prototype.getBoundingClientRect;
  Element.prototype.getBoundingClientRect = function (this: Element) {
    const w = 90;
    const box =
      this === list
        ? { left: 0, right: 300, top: 0, bottom: 40, width: 300, height: 40 }
        : { left: 10, right: 10 + w, top: 4, bottom: 32, width: w, height: 28 };
    return { ...box, x: box.left, y: box.top, toJSON: () => box } as DOMRect;
  };
  return () => {
    Element.prototype.getBoundingClientRect = orig;
  };
}

describe("TabStrip re-measures the ink when direction flips", () => {
  it("moves the ink to the RTL-mirrored offset on a dir flip, with no click", async () => {
    const unmount = await mount(
      <TabStrip tabs={TABS} active={0} onChange={() => {}} label="Dir proof" />,
    );
    const list = document.querySelector<HTMLElement>(".tab-strip")!;
    const ink = list.querySelector<HTMLElement>(".tab-ink")!;
    const restore = stubRects(list);

    // Establish the LTR baseline through the resize path (present before and
    // after this fix), so the only thing under test below is the dir flip.
    list.style.direction = "ltr";
    document.documentElement.setAttribute("dir", "ltr");
    await act(async () => {
      window.dispatchEvent(new Event("resize"));
      await new Promise((r) => setTimeout(r, 10));
    });
    expect(ink.style.transform).toBe("translate(10px, 4px)");

    // Flip to RTL without touching a tab. The pre-fix component only listened
    // for `resize`, which never fires for a direction change, so the ink kept
    // the LTR offset above. The MutationObserver on <html> must re-run the
    // measurement, and `position()` must read the new direction.
    list.style.direction = "rtl";
    document.documentElement.setAttribute("dir", "rtl");
    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });
    // RTL mirrors the origin to the physical right: list.right - tab.right
    // (300 - 100 = 200), negated for the physical transform.
    expect(ink.style.transform).toBe("translate(-200px, 4px)");

    restore();
    await unmount();
  });
});
