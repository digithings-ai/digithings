/**
 * The digiquant pipeline rail must scroll, never overlap.
 *
 * The rail is one horizontal scroll track holding three engine groups (research,
 * portfolio, execution). Each group holds fixed-width `shrink-0` phase cards, so
 * the groups must be `shrink-0` too. A group left at the default
 * `flex-shrink: 1` collapses below its own content width while its cards keep
 * theirs, and the groups then paint on top of each other — the rail reads as
 * overlapping cards with a broken label, and the horizontal scroll never engages
 * because `scrollWidth` collapses with the groups.
 *
 * This is a class-string contract, not a geometry test: happy-dom has no layout
 * engine, so measuring boxes would assert nothing. The browser check that proved
 * the fix is recorded in the PR (19 cards, `cardOverlaps: 0`, group width ==
 * group scrollWidth, rail scrollWidth 3711 > 1180).
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const src = readFileSync(fileURLToPath(new URL("./QuantSection.tsx", import.meta.url)), "utf8");

/**
 * The rail body, from the component signature to the end of its declaration.
 * Slicing to a fixed character offset is not safe here: it silently truncated
 * the last ~570 chars of this function, which meant the negative assertion below
 * only ever saw the head of the body.
 */
function pipelineRailBody(): string {
  const start = src.indexOf("function PipelineRail()");
  if (start === -1) throw new Error("PipelineRail not found");
  // `PipelineRail` is the last function in the module, so its declaration runs
  // to the end of the file.
  return src.slice(start);
}

describe("digiquant pipeline rail", () => {
  const rail = pipelineRailBody();

  it("keeps the engine groups from shrinking so the rail scrolls instead of overlapping", () => {
    // The group wrapper carries shrink-0; min-w-0 without shrink-0 is what let
    // the group collapse under its shrink-0 cards.
    expect(rail).toMatch(/className="flex shrink-0 items-stretch gap-\[0\.5rem\]"/);
    expect(rail).not.toMatch(/className="flex min-w-0 items-stretch/);
  });

  it("scrolls horizontally rather than wrapping", () => {
    expect(rail).toContain("overflow-x-auto");
  });

  it("gives every listitem a list that owns it", () => {
    // A `list` owns its `listitem` children directly. The engine groups sit
    // between the two, so the cards were grandchildren and screen readers lost
    // the item count and position (and could surface the cards as list items
    // with no list at all). Each engine is the list item, carrying the engine
    // name; the phases inside it are plain content, not orphan list items.
    expect(rail).toMatch(/role="list"\s+aria-label="digiquant pipeline phases"/);
    expect(rail).toMatch(/role="listitem"\s+aria-label=\{engine\.label\}/);
    expect(rail).not.toMatch(/role="group"/);
    expect(rail).not.toMatch(/role="listitem"\s+title=/);
  });
});