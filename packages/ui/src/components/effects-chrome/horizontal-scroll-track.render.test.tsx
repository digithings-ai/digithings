import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MotionProvider } from "../../motion/primitives";
import { HorizontalScrollTrack, HorizontalTrackStepper } from "./HorizontalScrollTrack";

const LABELS = ["Inputs", "Research", "Synthesis"];

function render() {
  return renderToStaticMarkup(
    <MotionProvider>
      <HorizontalScrollTrack
        ariaLabel="Pipeline stages"
        footer={<HorizontalTrackStepper labels={LABELS} />}
        header={(s) => <p>{`${s.count} stages, pinned=${s.pinned}`}</p>}
      >
        {LABELS.map((l) => (
          <article key={l}>{l} card</article>
        ))}
      </HorizontalScrollTrack>
    </MotionProvider>,
  );
}

describe("HorizontalScrollTrack (server / first paint / no-JS)", () => {
  it("renders the native snap strip, never the pin", () => {
    const html = render();
    expect(html).toContain('data-track="strip"');
    expect(html).not.toContain('data-track="pinned"');
    expect(html).toContain("snap-x");
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain("3 stages");
    expect(html).toContain("pinned=false");
  });

  it("makes every card a tab stop, in DOM order, inside a labelled list", () => {
    const html = render();
    expect(html).toContain('role="list"');
    expect(html).toContain('aria-label="Pipeline stages"');
    expect(html.match(/role="listitem"/g)?.length).toBe(3);
    expect(html.match(/tabindex="0"/g)?.length).toBe(3);
    expect(html.indexOf("Inputs card")).toBeLessThan(html.indexOf("Research card"));
    expect(html.indexOf("Research card")).toBeLessThan(html.indexOf("Synthesis card"));
  });

  it("shows every card and every stepper label with no JS", () => {
    const html = render();
    for (const l of LABELS) {
      expect(html).toContain(`${l} card`);
      expect(html).toContain(l);
    }
    expect(html).toContain("Pipeline stages");
    expect(html).toContain('aria-current="step"');
  });

  it("uses token stops in the edge fade, never a raw colour", () => {
    const html = render();
    expect(html).toContain("var(--ink)");
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(html).not.toMatch(/rgba?\(/);
  });
});
