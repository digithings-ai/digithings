/**
 * SSR tests for <TabStrip>'s aria-controls derivation.
 *
 * #2272: TabStrip's default (`linkPanels=true`, no `sharedPanel`) points every
 * tab's aria-controls at ITS OWN id — correct only when the consumer mounts
 * one role="tabpanel" per tab. Two shipped consumers (AttributionWorkspace,
 * PerformanceTearsheetView) instead mount a single, content-swapping panel keyed
 * to the active tab, so every INACTIVE tab's aria-controls dangled a
 * reference to an id that only exists while it is active. `sharedPanel`
 * fixes this by pointing every tab at the currently active tab's id instead.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { TabStrip, tabPanelId, type TabItem } from "./TabStrip";

const TABS: TabItem[] = [
  { id: "one", label: "One" },
  { id: "two", label: "Two" },
  { id: "three", label: "Three" },
];

describe("TabStrip aria-controls", () => {
  it("defaults to one aria-controls per tab, each pointing at its own id", () => {
    const html = renderToStaticMarkup(
      <TabStrip tabs={TABS} active={1} onChange={() => {}} label="Demo" />
    );
    expect(html).toContain(`aria-controls="${tabPanelId("Demo", "one")}"`);
    expect(html).toContain(`aria-controls="${tabPanelId("Demo", "two")}"`);
    expect(html).toContain(`aria-controls="${tabPanelId("Demo", "three")}"`);
  });

  it("sharedPanel points EVERY tab at the active tab's id, not its own", () => {
    const html = renderToStaticMarkup(
      <TabStrip tabs={TABS} active={1} onChange={() => {}} label="Demo" sharedPanel />
    );
    const activePanelId = tabPanelId("Demo", "two");
    // Every occurrence of aria-controls must be the active id -- none may
    // dangle a reference to "one" or "three", ids that do not exist in the
    // DOM while tab "two" is active.
    const matches = [...html.matchAll(/aria-controls="([^"]+)"/g)].map((m) => m[1]);
    expect(matches).toHaveLength(TABS.length);
    expect(matches.every((id) => id === activePanelId)).toBe(true);
    expect(html).not.toContain(`aria-controls="${tabPanelId("Demo", "one")}"`);
    expect(html).not.toContain(`aria-controls="${tabPanelId("Demo", "three")}"`);
  });

  it("linkPanels={false} omits aria-controls regardless of sharedPanel", () => {
    const html = renderToStaticMarkup(
      <TabStrip
        tabs={TABS}
        active={0}
        onChange={() => {}}
        label="Demo"
        linkPanels={false}
        sharedPanel
      />
    );
    expect(html).not.toContain("aria-controls");
  });
});
