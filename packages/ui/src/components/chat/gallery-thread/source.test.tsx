// @vitest-environment happy-dom
/**
 * Citation rows (#4552).
 *
 * `source-url` / `source-document` parts are converted by the runtime into a
 * single `source` part; before this component existed they fell through the
 * message part switch's `default` and were dropped, so a grounded answer showed
 * no provenance. These tests pin the two shapes: a web source renders as a
 * safe external link, a document as plain text.
 */
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { SourceMessagePartProps } from "@assistant-ui/react";
import { afterEach, describe, expect, it } from "vitest";

import { ThreadSource } from "./source";

function mount(ui: React.ReactElement) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  act(() => {
    root.render(ui);
  });
  return { host, unmount: () => act(() => root.unmount()) };
}

const urlSource = {
  type: "source",
  sourceType: "url",
  id: "src-1",
  url: "https://example.com/grounding",
  title: "Grounding page",
} as unknown as SourceMessagePartProps;

const documentSource = {
  type: "source",
  sourceType: "document",
  id: "src-2",
  title: "Vault note",
  mediaType: "text/markdown",
  filename: "note.md",
} as unknown as SourceMessagePartProps;

describe("ThreadSource", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("renders a url source as a safe external link", () => {
    const { host, unmount } = mount(<ThreadSource {...urlSource} />);
    const row = host.querySelector('[data-slot="aui_source-url"]');
    expect(row).not.toBeNull();
    expect(row?.getAttribute("href")).toBe("https://example.com/grounding");
    expect(row?.getAttribute("target")).toBe("_blank");
    expect(row?.getAttribute("rel")).toContain("noreferrer");
    expect(row?.textContent).toContain("Grounding page");
    unmount();
  });

  it("renders a document source as text with its title", () => {
    const { host, unmount } = mount(<ThreadSource {...documentSource} />);
    const row = host.querySelector('[data-slot="aui_source-document"]');
    expect(row).not.toBeNull();
    expect(row?.tagName).toBe("SPAN");
    expect(row?.textContent).toContain("Vault note");
    unmount();
  });

  it("falls back to the filename when a document has no title", () => {
    const { host, unmount } = mount(
      <ThreadSource
        {...({ ...documentSource, title: undefined } as SourceMessagePartProps)}
      />,
    );
    expect(host.textContent).toContain("note.md");
    unmount();
  });

  it("falls back to the url when a web source has no title", () => {
    const { host, unmount } = mount(
      <ThreadSource
        {...({ ...urlSource, title: undefined } as SourceMessagePartProps)}
      />,
    );
    expect(host.textContent).toContain("https://example.com/grounding");
    unmount();
  });

  it.each(["javascript:alert(1)", "data:text/html,<script>x</script>", ""])(
    "does not build a link from a non-http(s) url: %s",
    (url) => {
      const { host, unmount } = mount(
        <ThreadSource
          {...({ ...urlSource, url, title: "Suspicious" } as SourceMessagePartProps)}
        />,
      );
      // The row still renders (the citation is real), but nothing is clickable.
      expect(host.querySelector("a")).toBeNull();
      expect(host.querySelector('[data-slot="aui_source-url"]')).toBeNull();
      expect(host.textContent).toContain("Suspicious");
      unmount();
    },
  );
});
