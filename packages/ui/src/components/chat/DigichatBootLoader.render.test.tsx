import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DigichatBootLoader } from "./DigichatBootLoader";

function occurrences(html: string, needle: string) {
  return html.split(needle).length - 1;
}

describe("DigichatBootLoader", () => {
  it("renders the cube-loader shell with an accessible status label", () => {
    const html = renderToStaticMarkup(<DigichatBootLoader />);
    expect(html).toContain('class="dboot"');
    expect(html).toContain('role="status"');
    expect(html).toContain("Loading chat");
    expect(html).toContain("dboot-grid");
    expect(html).toContain("dboot-composer-wrap");
    expect(html).toContain('class="dboot-composer"');
    expect(html).toContain("dboot-plus");
    // Copy types in client-side; nothing is typed during SSR.
    expect(html).not.toContain("dboot-caret");
  });

  it("renders one suggestion row per suggestion with its example marker", () => {
    const html = renderToStaticMarkup(<DigichatBootLoader />);
    expect(occurrences(html, 'class="dboot-chip"')).toBe(4);
    expect(occurrences(html, "dboot-chip-mark")).toBe(4);
    expect(occurrences(html, "dboot-chip-text")).toBe(4);
  });

  it("accepts custom copy, suggestions, label and className", () => {
    const html = renderToStaticMarkup(
      <DigichatBootLoader
        welcome="Custom welcome"
        welcomeBody="Custom body"
        placeholder="Custom placeholder"
        suggestions={["Only one"]}
        label="Warming the chat"
        className="dc-embed-boot"
      />,
    );
    expect(html).toContain('class="dboot dc-embed-boot"');
    expect(html).toContain("Warming the chat");
    expect(occurrences(html, 'class="dboot-chip"')).toBe(1);
  });
});
