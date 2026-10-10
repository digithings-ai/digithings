import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MediaFrame } from "./MediaFrame";

const BASE = {
  caption: "A walkthrough of the sample flow",
  placeholderLabel: "recording to come",
  title: "sample walkthrough",
  badge: "Placeholder · no recording yet",
};

describe("MediaFrame", () => {
  it("renders a designed placeholder when there is no src", () => {
    const html = renderToStaticMarkup(<MediaFrame {...BASE} />);
    expect(html).toContain('data-state="placeholder"');
    expect(html).toContain("aspect-video");
    expect(html).toContain("[ recording to come ]");
    expect(html).toContain("sample walkthrough");
    expect(html).toContain("Placeholder · no recording yet");
    expect(html).toContain("A walkthrough of the sample flow");
    expect(html).toContain("var(--hair)");
    expect(html).not.toContain("<video");
    // the play glyph is present but disabled
    expect(html).toMatch(/<button[^>]*disabled=""/);
  });

  it("renders a muted, inline, non-autoplaying video when src is given", () => {
    const html = renderToStaticMarkup(<MediaFrame {...BASE} src="/rec.mp4" poster="/poster.png" />);
    expect(html).toContain('data-state="media"');
    expect(html).toContain("<video");
    expect(html).toContain('src="/rec.mp4"');
    expect(html).toContain('poster="/poster.png"');
    expect(html).toContain("controls");
    expect(html).toContain("muted");
    expect(html.toLowerCase()).toContain("playsinline");
    expect(html).toContain('preload="none"');
    expect(html).not.toContain("autoplay");
    expect(html).not.toContain("[ recording to come ]");
  });

  it("renders an image for kind=image with the caption as alt", () => {
    const html = renderToStaticMarkup(<MediaFrame {...BASE} kind="image" src="/still.png" />);
    expect(html).toContain("<img");
    expect(html).toContain('alt="A walkthrough of the sample flow"');
    expect(html).not.toContain("<video");
  });

  it("uses tokens only", () => {
    const html = renderToStaticMarkup(<MediaFrame {...BASE} />);
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(html).not.toMatch(/rgba?\(/);
  });
});
